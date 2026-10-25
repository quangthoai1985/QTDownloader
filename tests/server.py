"""Máy chủ HTTP thử nghiệm mô phỏng các tình huống khó của thực tế.

    python tests/server.py --port 8765

/file/<tên>?size=BYTES          tệp ngẫu nhiên tất định (cùng size → cùng nội dung)
    &rate=KB          giới hạn tốc độ MỖI kết nối (để thấy lợi ích đa kết nối)
    &norange=1        bỏ qua Range (trả 200)          &nolen=1   không gửi Content-Length
    &fail=0.2         xác suất đứt kết nối giữa chừng  &maxconn=N quá N kết nối đồng thời → 503
    &weak=1           ETag yếu                          &cap=BYTES mỗi phản hồi tối đa BYTES
    &ver=N            đổi nội dung/ETag (mô phỏng tệp bị cập nhật trên máy chủ)
/redirect/<tên>?…   302 → /file/<tên>?…
/cd?…               Content-Disposition tên tiếng Việt
/html               trang HTML
/hls/master.m3u8, /hls/media.m3u8, /hls/seg<i>.ts, /hls/enc.m3u8, /hls/live.m3u8
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

_cache: dict[tuple[int, int], bytes] = {}
_lock = threading.Lock()
_active: dict[str, int] = {}
STATS = {"requests": 0, "ranged": 0, "503": 0, "max_parallel": 0, "connections": set()}

GH_ASSET_SIZE = 1_234_567
HLS_SEGMENTS = 12
HLS_SEG_SIZE = 150_000


def blob(size: int, ver: int = 0) -> bytes:
    key = (size, ver)
    with _lock:
        if key not in _cache:
            _cache[key] = random.Random(size * 7919 + ver).randbytes(size)
        return _cache[key]


def sha256_of(size: int, ver: int = 0) -> str:
    return hashlib.sha256(blob(size, ver)).hexdigest()


def hls_segment(i: int) -> bytes:
    return random.Random(10_000 + i).randbytes(HLS_SEG_SIZE)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head: bool = False):
        u = urlsplit(self.path)
        q = {k: v[-1] for k, v in parse_qs(u.query).items()}
        STATS["requests"] += 1
        STATS["connections"].add(self.client_address)
        p = u.path
        if p.startswith("/gh/"):  # giả lập GitHub Releases API cho cơ chế kiểm tra cập nhật
            return self.serve_github(p[4:])
        if p.startswith("/sized/"):  # /sized/<size>/<tên>[.sha256] — để thử tự tìm checksum
            _, _, size, name = p.split("/", 3)
            if name.endswith(".sha256"):
                return self.simple(200, f"{sha256_of(int(size))} *{name[:-7]}\n".encode(), "text/plain")
            return self.serve_file(name, {**q, "size": size}, head)
        if p.startswith("/file/"):
            return self.serve_file(p[6:], q, head)
        if p.startswith("/redirect/"):
            self.send_response(302)
            self.send_header("Location", "/file/" + p[10:] + ("?" + u.query if u.query else ""))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if p == "/cd":
            return self.serve_file("ignored.bin", q, head,
                                   cd="attachment; filename*=UTF-8''" + quote("Tài liệu mẫu.pdf"))
        if p == "/html":
            body = b"<html><body>login</body></html>"
            return self.simple(200, body, "text/html; charset=utf-8")
        if p.startswith("/hls/"):
            return self.serve_hls(p[5:])
        if p.endswith(".sha256"):
            name = p.rsplit("/", 1)[-1][:-7]
            size = int(q.get("size", 0) or 0)
            if not size:
                return self.simple(404, b"no")
            return self.simple(200, f"{sha256_of(size)}  {name}\n".encode(), "text/plain")
        self.simple(404, b"not found")

    def simple(self, code: int, body: bytes, ctype: str = "text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_github(self, rest: str):
        """/gh/latest/<tag> · /gh/legacy/<tag> · /gh/latest/404 · /gh/latest/ratelimit · /gh/asset/<tên>"""
        import json
        base = f"http://{self.headers.get('Host')}/gh/asset/"
        kind, _, arg = rest.partition("/")
        if kind == "asset":
            if arg == "SHA256SUMS.txt":
                body = "".join(f"{sha256_of(GH_ASSET_SIZE)}  {n}\n" for v in ("9.9.9", "1.0.1")
                               for n in (f"QTDownloader-{v}-win64.zip", f"QTDownloader-{v}-setup.exe",
                                         f"TDownload-{v}-win64.zip"))
                return self.simple(200, body.encode(), "text/plain")
            return self.serve_file(arg, {"size": str(GH_ASSET_SIZE)}, False)
        if arg == "404":
            return self.simple(404, b'{"message":"Not Found"}', "application/json")
        if arg == "ratelimit":
            return self.simple(403, b'{"message":"API rate limit exceeded"}', "application/json")
        ver = arg.lstrip("v")
        names = [f"QTDownloader-{ver}-win64.zip", f"QTDownloader-{ver}-setup.exe", f"TDownload-{ver}-win64.zip"]
        if kind == "legacy":   # bản phát hành trước khi đổi tên: chỉ có gói TDownload-*.zip
            names = [f"TDownload-{ver}-win64.zip"]
        rel = {"tag_name": arg, "name": f"QT Downloader {ver}", "body": "## Có gì mới\n- Sửa lỗi", "draft": False,
               "html_url": f"https://github.com/x/QTDownloader/releases/tag/{arg}", "prerelease": False,
               "published_at": "2026-10-20T00:00:00Z",
               "assets": [{"name": n, "size": GH_ASSET_SIZE, "browser_download_url": base + n} for n in names]
                         + [{"name": "SHA256SUMS.txt", "size": 100, "browser_download_url": base + "SHA256SUMS.txt"}]}
        self.simple(200, json.dumps(rel).encode(), "application/json")

    def serve_hls(self, name: str):
        base = f"http://{self.headers.get('Host')}/hls/"
        if name == "master.m3u8":
            body = ("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\nlow.m3u8\n"
                    "#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720\nmedia.m3u8\n")
        elif name in ("media.m3u8", "low.m3u8", "enc.m3u8", "live.m3u8"):
            lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:4"]
            if name == "enc.m3u8":
                lines.append('#EXT-X-KEY:METHOD=AES-128,URI="key.bin"')
            for i in range(HLS_SEGMENTS):
                lines += ["#EXTINF:4.0,", f"seg{i}.ts" if i % 2 else base + f"seg{i}.ts"]
            if name != "live.m3u8":
                lines.append("#EXT-X-ENDLIST")
            body = "\n".join(lines) + "\n"
        elif name.startswith("seg") and name.endswith(".ts"):
            return self.simple(200, hls_segment(int(name[3:-3])), "video/mp2t")
        else:
            return self.simple(404, b"no")
        self.simple(200, body.encode(), "application/vnd.apple.mpegurl")

    def serve_file(self, name: str, q: dict, head: bool, cd: str = ""):
        size = int(q.get("size", 1_000_000))
        ver = int(q.get("ver", 0))
        data = blob(size, ver)
        rate = float(q.get("rate", 0)) * 1024
        etag = f'"v{ver}-{size}"'
        if q.get("weak"):
            etag = "W/" + etag
        maxconn = int(q.get("maxconn", 0))
        start, end = 0, size  # [start, end)
        status = 200
        rng = self.headers.get("Range")
        if_range = self.headers.get("If-Range")
        if rng and not q.get("norange") and (not if_range or if_range == etag):
            STATS["ranged"] += 1
            spec = rng.split("=", 1)[1]
            a, b = spec.split("-", 1)
            if a == "":
                start, end = max(0, size - int(b)), size
            else:
                start = int(a)
                end = min(size, int(b) + 1) if b else size
            if start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            cap = int(q.get("cap", 0))
            if cap and end - start > cap:
                end = start + cap
            status = 206
        key = name
        with _lock:
            if maxconn and _active.get(key, 0) >= maxconn:
                STATS["503"] += 1
                busy = True
            else:
                busy = False
                _active[key] = _active.get(key, 0) + 1
                STATS["max_parallel"] = max(STATS["max_parallel"], _active[key])
        if busy:
            self.send_response(503)
            self.send_header("Retry-After", "1")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", "Mon, 01 Jan 2024 00:00:00 GMT")
            if not q.get("norange"):
                self.send_header("Accept-Ranges", "bytes")
            if cd:
                self.send_header("Content-Disposition", cd)
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end - 1}/{size}")
            if q.get("nolen"):
                self.send_header("Connection", "close")
                self.close_connection = True
            else:
                self.send_header("Content-Length", str(end - start))
            self.end_headers()
            if head:
                return
            fail = float(q.get("fail", 0))
            cut = end
            if fail and random.random() < fail and end - start > 65536:
                cut = start + random.randint(1, end - start - 1)
            pos = start
            t0 = time.monotonic()
            while pos < cut:
                n = min(32768, cut - pos)
                self.wfile.write(data[pos:pos + n])
                pos += n
                if rate:
                    ahead = (pos - start) / rate - (time.monotonic() - t0)
                    if ahead > 0:
                        time.sleep(ahead)
            if cut < end:
                self.close_connection = True
                self.connection.close()
        except (ConnectionError, OSError):
            self.close_connection = True
        finally:
            with _lock:
                _active[key] -= 1


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start(port: int = 0) -> tuple[Server, str]:
    srv = Server(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    srv, base = start(a.port)
    print(f"Máy chủ thử nghiệm chạy tại {base}  (Ctrl+C để thoát)")
    print(f"  Ví dụ: {base}/file/test.bin?size=50000000&rate=800")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        srv.shutdown()

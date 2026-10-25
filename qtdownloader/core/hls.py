"""Tải luồng HLS (RFC 8216): chọn chất lượng, tải song song segment, ghép thành 1 tệp.

* Luồng có #EXT-X-KEY (AES-128/SAMPLE-AES/DRM) bị TỪ CHỐI — không giải mã nội dung được bảo vệ.
* Luồng trực tiếp (không có #EXT-X-ENDLIST) chưa hỗ trợ.
* fMP4 (#EXT-X-MAP) → ghép thành .mp4; MPEG-TS → .ts, tự remux sang .mp4 nếu có ffmpeg.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from . import models as M
from .fileio import mark_of_the_web
from .http_task import NET_ERRORS, WorkerInfo, _short
from .limiter import RateLimiter
from .probe import DownloadError, TransientError, http_error
from .util import filename_from_url, now, unique_path

log = logging.getLogger("qtdownloader.hls")

_ATTR = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')


def parse_attrs(s: str) -> dict[str, str]:
    return {k: v.strip('"') for k, v in _ATTR.findall(s)}


@dataclass
class Variant:
    url: str
    bandwidth: int = 0
    resolution: str = ""
    codecs: str = ""

    @property
    def label(self) -> str:
        parts = []
        if self.resolution:
            parts.append(self.resolution)
        if self.bandwidth:
            parts.append(f"{self.bandwidth / 1_000_000:.1f} Mbps")
        return " · ".join(parts) or self.url.rsplit("/", 1)[-1]


@dataclass
class MediaSegment:
    url: str
    duration: float = 0.0
    byterange: tuple[int, int] | None = None   # (offset, length)


@dataclass
class MediaPlaylist:
    segments: list[MediaSegment] = field(default_factory=list)
    init: MediaSegment | None = None
    key_method: str = "NONE"
    endlist: bool = False

    @property
    def encrypted(self) -> bool:
        return self.key_method.upper() not in ("", "NONE")

    @property
    def duration(self) -> float:
        return sum(s.duration for s in self.segments)


def _byterange(spec: str, last_end: dict, uri: str) -> tuple[int, int]:
    if "@" in spec:
        length, offset = spec.split("@", 1)
        length, offset = int(length), int(offset)
    else:
        length, offset = int(spec), last_end.get(uri, 0)
    last_end[uri] = offset + length
    return offset, length


def parse_playlist(text: str, base_url: str):
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    if not lines or not lines[0].startswith("#EXTM3U"):
        raise DownloadError("Không phải playlist HLS hợp lệ (#EXTM3U)")
    if any(ln.startswith("#EXT-X-STREAM-INF") for ln in lines):
        variants: list[Variant] = []
        pending: dict | None = None
        for ln in lines:
            if ln.startswith("#EXT-X-STREAM-INF:"):
                pending = parse_attrs(ln.split(":", 1)[1])
            elif ln and not ln.startswith("#") and pending is not None:
                bw = pending.get("BANDWIDTH") or pending.get("AVERAGE-BANDWIDTH") or "0"
                variants.append(Variant(urljoin(base_url, ln), int(bw) if bw.isdigit() else 0,
                                        pending.get("RESOLUTION", ""), pending.get("CODECS", "")))
                pending = None
        variants.sort(key=lambda v: v.bandwidth, reverse=True)
        return "master", variants
    pl = MediaPlaylist()
    duration = 0.0
    byterange: str | None = None
    last_end: dict[str, int] = {}
    for ln in lines:
        if ln.startswith("#EXTINF:"):
            try:
                duration = float(ln.split(":", 1)[1].split(",", 1)[0])
            except ValueError:
                duration = 0.0
        elif ln.startswith("#EXT-X-BYTERANGE:"):
            byterange = ln.split(":", 1)[1]
        elif ln.startswith("#EXT-X-KEY:"):
            method = parse_attrs(ln.split(":", 1)[1]).get("METHOD", "NONE")
            if method.upper() != "NONE":
                pl.key_method = method
        elif ln.startswith("#EXT-X-MAP:"):
            a = parse_attrs(ln.split(":", 1)[1])
            uri = urljoin(base_url, a.get("URI", ""))
            br = _byterange(a["BYTERANGE"], last_end, uri) if a.get("BYTERANGE") else None
            pl.init = MediaSegment(uri, 0.0, br)
        elif ln.startswith("#EXT-X-ENDLIST"):
            pl.endlist = True
        elif ln and not ln.startswith("#"):
            uri = urljoin(base_url, ln)
            br = _byterange(byterange, last_end, uri) if byterange else None
            pl.segments.append(MediaSegment(uri, duration, br))
            duration, byterange = 0.0, None
    return "media", pl


async def fetch_text(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    r = await client.get(url)
    if r.status_code != 200:
        raise http_error(r.status_code, r.headers.get("retry-after"))
    if len(r.content) > 20 * 1024 * 1024:
        raise DownloadError("Playlist quá lớn")
    return r.text, str(r.url)


async def probe_hls(client: httpx.AsyncClient, url: str) -> dict:
    text, final = await fetch_text(client, url)
    kind, data = parse_playlist(text, final)
    base = os.path.splitext(filename_from_url(url) or "video")[0]
    info = {"kind": "hls", "url": url, "final_url": final, "size": -1, "ranged": False,
            "content_type": "application/vnd.apple.mpegurl", "filename": base + ".ts",
            "variants": [], "status": 200, "etag": "", "last_modified": ""}
    if kind == "master":
        info["variants"] = [{"url": v.url, "label": v.label, "bandwidth": v.bandwidth,
                             "resolution": v.resolution} for v in data]
        if data:  # xem trước biến thể tốt nhất để biết có mã hoá / live không
            t2, f2 = await fetch_text(client, data[0].url)
            k2, pl = parse_playlist(t2, f2)
            data = pl if k2 == "media" else None
    if isinstance(data, MediaPlaylist):
        info.update(segments=len(data.segments), duration=data.duration, encrypted=data.encrypted,
                    live=not data.endlist, fmp4=data.init is not None)
        if data.init is not None:
            info["filename"] = base + ".mp4"
    return info


def find_ffmpeg(configured: str = "") -> str:
    if configured and os.path.isfile(configured):
        return configured
    return shutil.which("ffmpeg") or ""


class HlsTask:
    def __init__(self, engine, item: M.DownloadItem):
        self.engine = engine
        self.item = item
        self.settings = engine.settings
        self.loop = asyncio.get_running_loop()
        self.client: httpx.AsyncClient | None = None
        self.workers: dict[int, WorkerInfo] = {}
        self.limiter = RateLimiter(item.speed_limit_kb * 1024)
        self.segmap = None
        self.single_seg = None
        self.ranged = False
        self.speed = 0.0
        self.message = ""
        self._stop = False
        self._fatal: DownloadError | None = None
        self._bytes = 0

    def stop(self) -> None:
        self._stop = True

    def set_speed_limit(self, kb: int) -> None:
        self.item.speed_limit_kb = kb
        self.limiter.set_rate(kb * 1024)

    @property
    def tmpdir(self) -> str:
        return self.item.path + ".tdhls"

    async def run(self) -> None:
        item = self.item
        item.status = M.CONNECTING
        item.error = ""
        item.last_try = now()
        self.engine.changed(item)
        ticker = asyncio.create_task(self._ticker())
        try:
            self.client = self.engine.make_client(item, http2=False)
            pl = await self._load_playlist()
            if self._stop:
                return self._paused()
            await self._download_segments(pl)
            if self._fatal:
                raise self._fatal
            if self._stop:
                return self._paused()
            await self._merge(pl)
        except asyncio.CancelledError:
            self._paused()
            raise
        except DownloadError as e:
            self._error(str(e))
        except NET_ERRORS as e:
            self._error(f"Lỗi mạng: {_short(e)}")
        except Exception as e:
            log.exception("Lỗi HLS %s", item.url)
            self._error(f"Lỗi nội bộ: {_short(e)}")
        finally:
            ticker.cancel()
            if self.client is not None:
                await self.client.aclose()

    async def _get_text(self, url: str) -> tuple[str, str]:
        attempt = 0
        while True:
            try:
                return await fetch_text(self.client, url)
            except (TransientError, *NET_ERRORS) as e:
                attempt += 1
                if attempt > self.settings.max_retries or self._stop:
                    raise DownloadError(f"Không tải được playlist: {_short(e)}") from e
                await asyncio.sleep(min(30, 2 ** attempt))

    async def _load_playlist(self) -> MediaPlaylist:
        item = self.item
        text, final = await self._get_text(item.url)
        kind, data = parse_playlist(text, final)
        if kind == "master":
            if not data:
                raise DownloadError("Playlist chính không có biến thể nào")
            chosen = item.hls.get("variant") or data[0].url
            item.hls["variant"] = chosen
            item.hls["variant_label"] = next((v.label for v in data if v.url == chosen), "")
            text, final = await self._get_text(chosen)
            kind, data = parse_playlist(text, final)
            if kind != "media":
                raise DownloadError("Biến thể đã chọn không phải playlist media")
        pl: MediaPlaylist = data
        if pl.encrypted:
            raise DownloadError(f"Luồng được mã hoá ({pl.key_method}) — QT Downloader không giải mã nội dung "
                                "được bảo vệ (DRM)")
        if not pl.endlist:
            raise DownloadError("Đây là luồng trực tiếp (live) — chưa hỗ trợ")
        if not pl.segments:
            raise DownloadError("Playlist không có segment nào")
        item.hls["total"] = len(pl.segments)
        item.hls["duration"] = pl.duration
        if pl.init is not None and item.filename.lower().endswith(".ts") and not item.hls.get("done"):
            item.filename = unique_path(item.save_dir, item.filename[:-3] + ".mp4")
        return pl

    def _seg_path(self, i: int) -> str:
        return os.path.join(self.tmpdir, f"{i:06d}.seg")

    async def _download_segments(self, pl: MediaPlaylist) -> None:
        item = self.item
        os.makedirs(self.tmpdir, exist_ok=True)
        done = {i for i in item.hls.get("done", []) if os.path.exists(self._seg_path(i))}
        if pl.init is not None and not os.path.exists(self._seg_path(-1)):
            await self._fetch_segment(WorkerInfo(0, ""), pl.init, self._seg_path(-1))
        item.downloaded = sum(os.path.getsize(self._seg_path(i)) for i in done)
        item.hls["done"] = sorted(done)
        item.status = M.DOWNLOADING
        self.engine.changed(item, persist=True)
        todo: asyncio.Queue[int] = asyncio.Queue()
        for i in range(len(pl.segments)):
            if i not in done:
                todo.put_nowait(i)
        n = max(1, min(16, item.connections or self.settings.max_connections))
        last_save = time.monotonic()

        async def worker(wid: int) -> None:
            nonlocal last_save
            w = WorkerInfo(wid, "")
            self.workers[wid] = w
            try:
                while not (self._stop or self._fatal):
                    try:
                        i = todo.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    w.state = f"Segment {i + 1}/{len(pl.segments)}"
                    size = await self._fetch_segment(w, pl.segments[i], self._seg_path(i))
                    if size is None:
                        return
                    done.add(i)
                    item.downloaded += size
                    if time.monotonic() - last_save > 3:
                        item.hls["done"] = sorted(done)
                        self.engine.persist(item)
                        last_save = time.monotonic()
            finally:
                self.workers.pop(wid, None)

        await asyncio.gather(*(worker(k + 1) for k in range(n)))
        item.hls["done"] = sorted(done)
        self.engine.persist(item)
        if not self._stop and not self._fatal and len(done) < len(pl.segments):
            self._fatal = DownloadError("Một số segment không tải được")

    async def _fetch_segment(self, w: WorkerInfo, seg: MediaSegment, path: str) -> int | None:
        headers = {"Accept-Encoding": "identity"}
        if seg.byterange:
            off, length = seg.byterange
            headers["Range"] = f"bytes={off}-{off + length - 1}"
        attempt = 0
        while not (self._stop or self._fatal):
            try:
                buf = bytearray()
                async with self.client.stream("GET", seg.url, headers=headers) as r:
                    if r.status_code not in (200, 206):
                        raise http_error(r.status_code, r.headers.get("retry-after"))
                    async for chunk in r.aiter_raw(64 * 1024):
                        if self.limiter.rate > 0:
                            await self.limiter.consume(len(chunk))
                        if self.engine.limiter.rate > 0:
                            await self.engine.limiter.consume(len(chunk))
                        if self._stop:
                            return None
                        buf += chunk
                        w.bytes_tick += len(chunk)
                        w.total += len(chunk)
                        self._bytes += len(chunk)
                await self.loop.run_in_executor(self.engine.io_pool, _write_file, path, bytes(buf))
                return len(buf)
            except DownloadError as e:
                if not e.retryable:
                    self._fatal = e
                    return None
                err: BaseException = e
            except NET_ERRORS as e:
                err = e
            attempt += 1
            if attempt > self.settings.max_retries:
                self._fatal = DownloadError(f"Segment lỗi sau {attempt - 1} lần thử: {_short(err)}")
                return None
            w.state = f"Lỗi: {_short(err)} — thử lại lần {attempt}"
            await asyncio.sleep(min(30, 2 ** (attempt - 1)))
        return None

    async def _merge(self, pl: MediaPlaylist) -> None:
        item = self.item
        item.status = M.MERGING
        self.engine.changed(item)
        paths = ([self._seg_path(-1)] if pl.init is not None else []) + [
            self._seg_path(i) for i in range(len(pl.segments))]
        if os.path.exists(item.path):
            item.filename = unique_path(item.save_dir, item.filename)
        out = item.path
        size = await self.loop.run_in_executor(self.engine.io_pool, _concat, paths, out + ".tdpart")
        os.replace(out + ".tdpart", out)
        ffmpeg = find_ffmpeg(self.settings.ffmpeg_path)
        if out.lower().endswith(".ts") and ffmpeg:
            mp4 = os.path.join(item.save_dir, unique_path(item.save_dir, item.filename[:-3] + ".mp4"))
            ok = await self.loop.run_in_executor(None, _remux, ffmpeg, out, mp4)
            if ok:
                os.remove(out)
                item.filename = os.path.basename(mp4)
                size = os.path.getsize(mp4)
            else:
                self.message = "ffmpeg không chuyển được sang MP4 — giữ tệp .ts"
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        mark_of_the_web(item.path, item.url, item.page_url or item.referer)
        item.size = item.downloaded = size
        item.hls.pop("done", None)
        item.status = M.COMPLETED
        item.completed = now()
        self.engine.changed(item, persist=True)
        self.engine.emit("completed", item)

    async def _ticker(self) -> None:
        last_t, last_b = time.monotonic(), 0
        while True:
            await asyncio.sleep(0.5)
            t = time.monotonic()
            d = t - last_t
            inst = (self._bytes - last_b) / d
            self.speed = inst if self.speed == 0 else self.speed * 0.6 + inst * 0.4
            for w in self.workers.values():
                ws = w.bytes_tick / d
                w.speed = ws if w.speed == 0 else w.speed * 0.6 + ws * 0.4
                w.bytes_tick = 0
            last_t, last_b = t, self._bytes

    def _paused(self) -> None:
        self.item.status = M.QUEUED if self.engine.requeue_on_stop(self.item) else M.PAUSED
        self.engine.changed(self.item, persist=True)

    def _error(self, msg: str) -> None:
        self.item.status = M.ERROR
        self.item.error = msg
        self.engine.changed(self.item, persist=True)
        self.engine.emit("error", self.item)


def _write_file(path: str, data: bytes) -> None:
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _concat(paths: list[str], out: str) -> int:
    total = 0
    with open(out, "wb") as f:
        for p in paths:
            with open(p, "rb") as src:
                while chunk := src.read(4 * 1024 * 1024):
                    f.write(chunk)
                    total += len(chunk)
    return total


def _remux(ffmpeg: str, src: str, dst: str) -> bool:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-c", "copy",
                            "-movflags", "+faststart", dst], capture_output=True, timeout=3600,
                           creationflags=flags)
        return r.returncode == 0 and os.path.exists(dst)
    except (OSError, subprocess.SubprocessError):
        return False

import hashlib
import json
import os
import socket
import time
import urllib.request

import pytest

import server as test_server
from conftest import wait_done, wait_until
from tdownload.core.engine import Engine

MB = 1024 * 1024


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def add(eng, url, **kw):
    return eng.call_sync(eng.add, url, **kw)


def test_multi_connection_is_faster_and_correct(engine, srv):
    size = 6 * MB
    url = f"{srv}/file/speed.bin?size={size}&rate=800"
    t0 = time.monotonic()
    s1 = wait_done(engine, add(engine, url, connections=1, filename="one.bin"))
    t1 = time.monotonic() - t0
    t0 = time.monotonic()
    s8 = wait_done(engine, add(engine, url, connections=8, filename="eight.bin"))
    t8 = time.monotonic() - t0
    assert s1["status"] == s8["status"] == "completed"
    expected = test_server.sha256_of(size)
    assert sha(s1["path"]) == expected and sha(s8["path"]) == expected
    assert t8 < t1 / 2.5, (t1, t8)
    assert not os.path.exists(s8["path"] + ".tdpart")


def test_pause_and_resume_after_restart(tmp_path, srv):
    size = 8 * MB
    url = f"{srv}/file/resume.bin?size={size}&rate=600"
    data = tmp_path / "data"
    eng = Engine(data, start_api=False)
    eng.start()
    ident = add(eng, url, save_dir=str(tmp_path / "dl"), connections=4)
    wait_until(lambda: eng.snapshot["items"].get(ident, {}).get("downloaded", 0) > 3 * MB)
    eng.call_sync(eng.pause, ident)
    paused = eng.snapshot["items"][ident]
    eng.shutdown()
    eng2 = Engine(data, start_api=False)
    eng2.start()
    try:
        it = eng2.items[ident]
        assert it.status == "paused"
        saved = sum(p - s for s, e, p in it.segments)
        assert saved > 2 * MB, "phải nhớ được phần đã tải"
        before = test_server.STATS["ranged"]
        eng2.call_sync(eng2.resume, ident)
        s = wait_done(eng2, ident)
        assert s["status"] == "completed", s["error"]
        assert sha(s["path"]) == test_server.sha256_of(size)
        assert test_server.STATS["ranged"] > before
    finally:
        eng2.shutdown()
    assert paused["status"] in ("paused", "downloading")


def test_server_without_range_support(engine, srv):
    size = 3 * MB
    s = wait_done(engine, add(engine, f"{srv}/file/nr.bin?size={size}&norange=1", connections=8))
    assert s["status"] == "completed", s["error"]
    assert s["resumable"] is False
    assert sha(s["path"]) == test_server.sha256_of(size)


def test_unknown_length(engine, srv):
    size = 2 * MB + 123
    s = wait_done(engine, add(engine, f"{srv}/file/nl.bin?size={size}&nolen=1&norange=1"))
    assert s["status"] == "completed", s["error"]
    assert s["size"] == size
    assert sha(s["path"]) == test_server.sha256_of(size)


def test_flaky_connections_are_retried(engine, srv):
    size = 6 * MB
    s = wait_done(engine, add(engine, f"{srv}/file/flaky.bin?size={size}&fail=0.35", connections=6), 90)
    assert s["status"] == "completed", s["error"]
    assert sha(s["path"]) == test_server.sha256_of(size)


def test_connection_limit_server_reduces_connections(engine, srv):
    # đủ lớn để engine muốn mở > 2 kết nối (ngưỡng chia đoạn tối thiểu 1 MB)
    size = 12 * MB
    test_server.STATS["503"] = 0
    url = f"{srv}/file/limited.bin?size={size}&maxconn=2&rate=2500"
    s = wait_done(engine, add(engine, url, connections=8), 60)
    assert s["status"] == "completed", s["error"]
    assert sha(s["path"]) == test_server.sha256_of(size)
    assert test_server.STATS["503"] >= 1
    assert engine.host_caps.get("127.0.0.1", 8) <= 2


def test_short_range_responses(engine, srv):
    size = 5 * MB
    s = wait_done(engine, add(engine, f"{srv}/file/cap.bin?size={size}&cap=300000", connections=4))
    assert s["status"] == "completed", s["error"]
    assert sha(s["path"]) == test_server.sha256_of(size)


def test_global_speed_limit(engine, srv):
    engine.call_sync(engine.update_settings, {"global_speed_limit_kb": 400})
    t0 = time.monotonic()
    s = wait_done(engine, add(engine, f"{srv}/file/lim.bin?size={2 * MB}", connections=4))
    took = time.monotonic() - t0
    assert s["status"] == "completed"
    assert took >= 4.0, took   # 2048 KB / 400 KB/s ≈ 5 s


def test_resource_changed_restarts(tmp_path, srv):
    size = 6 * MB
    data = tmp_path / "data"
    eng = Engine(data, start_api=False)
    eng.start()
    ident = add(eng, f"{srv}/file/chg.bin?size={size}&rate=700&ver=1", save_dir=str(tmp_path / "dl"))
    wait_until(lambda: eng.snapshot["items"].get(ident, {}).get("downloaded", 0) > MB)
    eng.call_sync(eng.pause, ident)
    # tệp trên máy chủ được cập nhật (ETag khác) → không được trộn dữ liệu cũ/mới
    eng.items[ident].url = f"{srv}/file/chg.bin?size={size}&ver=2"
    eng.call_sync(eng.resume, ident)
    s = wait_done(eng, ident)
    eng.shutdown()
    assert s["status"] == "completed", s["error"]
    assert sha(s["path"]) == test_server.sha256_of(size, 2)


def test_redirect_content_disposition_and_mirrors(engine, srv):
    s = wait_done(engine, add(engine, f"{srv}/cd?size=200000"))
    assert s["status"] == "completed"
    size = 4 * MB
    url = f"{srv}/redirect/m.bin?size={size}&rate=900"
    mirror = f"{srv}/file/m.bin?size={size}&rate=900"
    s2 = wait_done(engine, add(engine, url, mirrors=[mirror], connections=4, filename="mirror.bin"))
    assert s2["status"] == "completed", s2["error"]
    assert sha(s2["path"]) == test_server.sha256_of(size)


def test_content_disposition_name_used_by_probe(engine, srv):
    info = engine.call_sync(engine.probe_url, f"{srv}/cd?size=1000")
    assert info["filename"] == "Tài liệu mẫu.pdf"
    assert info["ranged"] is True and info["size"] == 1000
    html = engine.call_sync(engine.probe_url, f"{srv}/html")
    assert html["content_type"].startswith("text/html")


def test_checksum_verification_and_sidecar(engine, srv):
    size = 1500 * 1024
    good = "sha256:" + test_server.sha256_of(size)
    s = wait_done(engine, add(engine, f"{srv}/file/ck.bin?size={size}", checksum=good))
    assert s["checksum_ok"] is True
    s = wait_done(engine, add(engine, f"{srv}/file/ck2.bin?size={size}", checksum="sha256:" + "0" * 64))
    assert s["checksum_ok"] is False
    engine.call_sync(engine.update_settings, {"auto_checksum_sidecar": True})
    s = wait_done(engine, add(engine, f"{srv}/sized/{size}/side.bin"))
    assert s["checksum"] == good and s["checksum_ok"] is True


def test_hls_master_playlist(engine, srv):
    info = engine.call_sync(engine.probe_url, f"{srv}/hls/master.m3u8")
    assert info["kind"] == "hls" and len(info["variants"]) == 2
    assert info["variants"][0]["resolution"] == "1280x720"
    s = wait_done(engine, add(engine, f"{srv}/hls/master.m3u8", filename="video.ts"))
    assert s["status"] == "completed", s["error"]
    expected = b"".join(test_server.hls_segment(i) for i in range(test_server.HLS_SEGMENTS))
    with open(s["path"], "rb") as f:
        assert f.read() == expected
    assert not os.path.exists(s["path"] + ".tdhls")


@pytest.mark.parametrize("name,msg", [("enc.m3u8", "mã hoá"), ("live.m3u8", "trực tiếp")])
def test_hls_refuses_encrypted_and_live(engine, srv, name, msg):
    s = wait_done(engine, add(engine, f"{srv}/hls/{name}"))
    assert s["status"] == "error" and msg in s["error"]


def test_queue_respects_max_concurrent(engine, srv):
    engine.call_sync(engine.update_settings, {"max_concurrent": 2})
    ids = [add(engine, f"{srv}/file/q{i}.bin?size={MB}&rate=1500", queue=True, connections=2) for i in range(5)]
    events = []
    engine.listeners.append(lambda k, p: events.append(k))
    engine.call_sync(engine.start_queue)
    peak = 0
    end = time.monotonic() + 60
    while time.monotonic() < end:
        snap = engine.snapshot["items"]
        peak = max(peak, sum(1 for i in ids if snap.get(i, {}).get("active")))
        if all(snap.get(i, {}).get("status") == "completed" for i in ids):
            break
        time.sleep(0.05)
    assert all(engine.snapshot["items"][i]["status"] == "completed" for i in ids)
    assert peak <= 2
    wait_until(lambda: "queue_finished" in events, 5)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_local_api_origin_rules(tmp_path, srv):
    port = _free_port()
    eng = Engine(tmp_path / "data", start_api=False)
    eng.settings.api_port = port
    eng.start_api = True
    eng.start()
    try:
        base = f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(base + "/api/ping") as r:
            assert json.loads(r.read())["app"] == "TDownload"

        def post(origin):
            body = json.dumps({"url": f"{srv}/file/api.bin?size=1000", "referer": "https://x"}).encode()
            req = urllib.request.Request(base + "/api/add", body, {"Content-Type": "application/json",
                                                                   "Origin": origin})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code

        assert post("https://evil.example") == 403
        assert post("chrome-extension://abcdefghijklmnop") == 200
        wait_until(lambda: any(i.referer == "https://x" for i in eng.items.values()))
    finally:
        eng.shutdown()


@pytest.mark.skipif(os.name != "nt", reason="Zone.Identifier chỉ có trên NTFS/Windows")
def test_mark_of_the_web(engine, srv):
    s = wait_done(engine, add(engine, f"{srv}/file/motw.exe?size=5000", referer="https://trang-nguon.vn/a"))
    assert s["status"] == "completed"
    with open(s["path"] + ":Zone.Identifier", encoding="utf-8") as f:
        zone = f.read()
    assert "ZoneId=3" in zone and "HostUrl=" in zone and "ReferrerUrl=https://trang-nguon.vn/a" in zone

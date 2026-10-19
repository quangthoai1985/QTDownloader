"""Cơ chế phát hiện phiên bản mới (GitHub Releases giả lập trong tests/server.py)."""

import server as test_server
from conftest import wait_done, wait_until
from tdownload import __version__
from tdownload.core.updater import is_newer, parse_version


def test_version_compare():
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("2.0") == (2, 0, 0)
    assert parse_version("ban-moi") is None
    assert is_newer("v1.0.1", "1.0.0")
    assert is_newer("v2.0", "1.9.9")
    assert not is_newer("v1.0.0", "1.0.0")
    assert not is_newer("v0.9.0", "1.0.0")
    assert not is_newer("latest", "1.0.0")


def test_detects_newer_release_and_downloads_it(engine, srv):
    events = []
    engine.listeners.append(lambda k, p: events.append((k, p)))
    engine.update_url = f"{srv}/gh/latest/v9.9.9"
    r = engine.call_sync(engine.check_update, True)
    assert r["status"] == "newer"
    info = r["info"]
    assert info["version"] == "9.9.9" and info["asset_name"] == "TDownload-9.9.9-win64.zip"
    assert info["sha256"] == test_server.sha256_of(test_server.GH_ASSET_SIZE)
    assert any(k == "update_available" for k, _ in events)
    wait_until(lambda: (engine.snapshot.get("update") or {}).get("version") == "9.9.9", 5)
    ident = engine.call_sync(engine.download_update)
    s = wait_done(engine, ident)
    assert s["status"] == "completed" and s["checksum_ok"] is True
    assert s["filename"] == "TDownload-9.9.9-win64.zip"


def test_current_version_is_latest(engine, srv):
    engine.update_url = f"{srv}/gh/latest/v{__version__}"
    assert engine.call_sync(engine.check_update, True)["status"] == "latest"


def test_skipped_version_is_silent_on_auto_check(engine, srv):
    events = []
    engine.listeners.append(lambda k, p: events.append(k))
    major, minor, patch = parse_version(__version__)
    newer = f"{major}.{minor}.{patch + 1}"              # luôn mới hơn bản đang chạy, kể cả sau khi tăng phiên bản
    engine.update_url = f"{srv}/gh/latest/v{newer}"
    engine.call_sync(engine.skip_update, newer)
    assert engine.call_sync(engine.check_update, False)["status"] == "newer"
    assert "update_available" not in events            # tự kiểm tra: im lặng với bản đã bỏ qua
    engine.call_sync(engine.check_update, True)
    assert "update_available" in events                # kiểm tra thủ công: vẫn báo


def test_errors_are_reported_not_raised(engine, srv):
    engine.update_url = f"{srv}/gh/latest/404"
    r = engine.call_sync(engine.check_update, True)
    assert r["status"] == "error" and "riêng tư" in r["error"]
    engine.update_url = f"{srv}/gh/latest/ratelimit"
    assert "giới hạn" in engine.call_sync(engine.check_update, True)["error"]
    assert engine.settings.last_update_check > 0

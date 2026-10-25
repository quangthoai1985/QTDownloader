"""Cơ chế phát hiện phiên bản mới (GitHub Releases giả lập trong tests/server.py)."""

import time

import pytest
import server as test_server
from conftest import wait_done, wait_until
from qtdownloader import __version__
from qtdownloader.core.updater import is_newer, parse_version


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
    assert info["version"] == "9.9.9" and info["asset_name"] == "QTDownloader-9.9.9-win64.zip"
    assert info["sha256"] == test_server.sha256_of(test_server.GH_ASSET_SIZE)
    assert any(k == "update_available" for k, _ in events)
    wait_until(lambda: (engine.snapshot.get("update") or {}).get("version") == "9.9.9", 5)
    ident = engine.call_sync(engine.download_update)
    s = wait_done(engine, ident)
    assert s["status"] == "completed" and s["checksum_ok"] is True
    assert s["filename"] == "QTDownloader-9.9.9-win64.zip"


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


def test_installed_copy_downloads_setup(engine, srv):
    """Bản đã cài bằng bộ cài → tải bộ cài mới (kiểm SHA-256), không tải zip."""
    engine.installed = True
    engine.update_url = f"{srv}/gh/latest/v9.9.9"
    info = engine.call_sync(engine.check_update, True)["info"]
    assert info["setup_name"] == "QTDownloader-9.9.9-setup.exe"
    assert info["setup_sha256"] == test_server.sha256_of(test_server.GH_ASSET_SIZE)
    assert info["asset_name"] == "QTDownloader-9.9.9-win64.zip"   # tên mới được ưu tiên hơn bản sao tên cũ
    s = wait_done(engine, engine.call_sync(engine.download_update))
    assert s["status"] == "completed" and s["checksum_ok"] is True
    assert s["filename"] == "QTDownloader-9.9.9-setup.exe"


def test_release_without_new_names_still_found(engine, srv):
    """Bản phát hành chỉ có gói tên cũ TDownload-*.zip vẫn được nhận (bản cài cũng rơi về zip)."""
    engine.installed = True
    engine.update_url = f"{srv}/gh/legacy/v9.9.9"
    info = engine.call_sync(engine.check_update, True)["info"]
    assert info["asset_name"] == "TDownload-9.9.9-win64.zip" and info["setup_url"] == ""
    s = wait_done(engine, engine.call_sync(engine.download_update))
    assert s["filename"] == "TDownload-9.9.9-win64.zip" and s["checksum_ok"] is True


def test_is_installed(tmp_path):
    from qtdownloader.core.updater import is_installed
    exe = tmp_path / "QTDownloader.exe"
    exe.write_bytes(b"")
    assert not is_installed(str(exe))
    (tmp_path / "unins000.exe").write_bytes(b"")
    assert is_installed(str(exe))
    assert not is_installed()          # chạy từ mã nguồn (không đóng gói)


def test_auto_check_prepares_setup_in_background(engine, srv):
    """Như QT PDF Pro: tự kiểm tra thấy bản mới → tải ngầm bộ cài (không thêm vào danh sách) → sẵn sàng cài."""
    events = []
    engine.listeners.append(lambda k, p: events.append((k, p)))
    engine.installed = True
    engine.update_url = f"{srv}/gh/latest/v9.9.9"
    assert engine.call_sync(engine.check_update, False)["status"] == "newer"
    avail = next(p for k, p in events if k == "update_available")
    assert avail["auto_download"] is True and avail["manual"] is False
    wait_until(lambda: any(k == "update_ready" for k, _ in events), 20)
    ready = next(p for k, p in events if k == "update_ready")
    path = engine.updates_dir / "QTDownloader-9.9.9-setup.exe"
    assert ready["path"] == str(path) and path.stat().st_size == test_server.GH_ASSET_SIZE
    assert not list(engine.updates_dir.glob("*.part"))
    assert engine.snapshot["items"] == {} or all("setup" not in i["filename"] for i in engine.snapshot["items"].values())
    wait_until(lambda: (engine.snapshot.get("update_state") or {}).get("stage") == "ready", 5)
    # gọi lại không tải lần hai
    assert engine.call_sync(engine.prepare_update) is True
    assert engine.update_state["stage"] == "ready"


def test_no_background_download_for_portable_or_opt_out(engine, srv):
    events = []
    engine.listeners.append(lambda k, p: events.append(k))
    engine.update_url = f"{srv}/gh/latest/v9.9.9"
    engine.installed = False                       # bản giải nén: chỉ báo
    engine.call_sync(engine.check_update, False)
    engine.installed = True
    engine.call_sync(engine.update_settings, {"auto_download_updates": False})
    engine.call_sync(engine.check_update, False)
    time.sleep(0.5)
    assert events.count("update_available") == 2 and "update_ready" not in events
    assert engine.update_state is None


def test_bad_sha_is_rejected(tmp_path):
    import asyncio
    import httpx
    from qtdownloader.core.updater import UpdateCheckError, download_verified

    async def run():
        transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"x" * 1000))
        async with httpx.AsyncClient(transport=transport) as c:
            with pytest.raises(UpdateCheckError, match="SHA-256"):
                await download_verified(c, "https://h/a.exe", tmp_path / "a.exe", "0" * 64)
            with pytest.raises(UpdateCheckError, match="thiếu"):
                await download_verified(c, "https://h/a.exe", tmp_path / "a.exe", "")
    asyncio.run(run())
    assert list(tmp_path.iterdir()) == []


def test_startup_update_reports_upgrade_and_cleans(engine, srv):
    from qtdownloader.core import updater as U
    engine.updates_dir.mkdir(parents=True)
    for name in ("QTDownloader-1.0.0-setup.exe", "QTDownloader-99.0.0-setup.exe", "x.part"):
        (engine.updates_dir / name).write_bytes(b"1")
    engine.call_sync(engine.update_settings, {"last_run_version": "1.0.3", "check_updates": False})
    assert engine.call_sync(engine.startup_update, 0) == {"updated_from": "1.0.3"}
    assert engine.settings.last_run_version == U.__version__
    assert sorted(p.name for p in engine.updates_dir.iterdir()) == ["QTDownloader-99.0.0-setup.exe"]
    assert engine.call_sync(engine.startup_update, 0) == {"updated_from": ""}

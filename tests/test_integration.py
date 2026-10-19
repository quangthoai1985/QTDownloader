"""Giao thức tdownload://, khởi động cùng Windows và luồng extension khi app chưa chạy.

Registry chỉ được ghi vào khoá tạm HKCU\\Software\\TDownloadTest\\<ngẫu nhiên> rồi xoá — không đụng khoá thật.
"""

import os
import shutil
import subprocess
import sys
import uuid

import pytest

from tdownload.core import integration as I
from tdownload.core.settings import Settings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
win_only = pytest.mark.skipif(sys.platform != "win32", reason="chỉ có registry trên Windows")


def test_parse_protocol_open():
    assert I.parse_protocol_url("tdownload://open") == {"action": "open", "minimized": False}
    assert I.parse_protocol_url("tdownload://open/") == {"action": "open", "minimized": False}
    assert I.parse_protocol_url("TDownload://") == {"action": "open", "minimized": False}
    assert I.parse_protocol_url("tdownload://open?minimized=1")["minimized"] is True
    assert I.parse_protocol_url("https://example.com/a.zip") is None
    assert I.parse_protocol_url("tdownload://xoa-het") is None


def test_parse_protocol_add():
    p = I.parse_protocol_url("tdownload://add?url=https%3A%2F%2Fh.vn%2Ft%E1%BB%87p%20a.zip%3Fx%3D1%26y%3D2"
                             "&referer=https%3A%2F%2Fh.vn%2F&filename=t%E1%BB%87p.zip")
    assert p == {"action": "add", "url": "https://h.vn/tệp a.zip?x=1&y=2", "referer": "https://h.vn/",
                 "filename": "tệp.zip", "minimized": False}
    assert I.parse_protocol_url("tdownload:add?url=http://a/b")["url"] == "http://a/b"
    assert I.parse_protocol_url("tdownload://add/?url=http://a/b")["url"] == "http://a/b"
    # chỉ nhận http(s) — không mở file:, javascript:, …
    assert I.parse_protocol_url("tdownload://add?url=file%3A%2F%2F%2FC%3A%2Fx") is None
    assert I.parse_protocol_url("tdownload://add") is None


def test_parse_launch_args():
    a = I.parse_launch_args(["https://a/1.zip", "tdownload://add?url=http%3A%2F%2Fb%2F2.zip&referer=http%3A%2F%2Fb%2F",
                             "tdownload://open", "rác"])
    assert a.adds == [{"url": "https://a/1.zip"},
                      {"url": "http://b/2.zip", "referer": "http://b/", "from_protocol": True}]
    assert a.minimized is False
    assert I.parse_launch_args(["--minimized"]).minimized is True
    assert I.parse_launch_args(["tdownload://open?minimized=1"]).minimized is True
    assert I.parse_launch_args(["tdownload://open?minimized=1"]).adds == []


def test_app_command_quotes_paths():
    cmd = I.app_command('"%1"')
    assert cmd.startswith('"') and cmd.endswith('"%1"')
    if not getattr(sys, "frozen", False):
        assert "run_tdownload.py" in cmd          # đường dẫn tuyệt đối: trình duyệt chạy ở thư mục bất kỳ
        assert "pythonw" in cmd.lower() or not os.path.exists(os.path.join(os.path.dirname(sys.executable),
                                                                          "pythonw.exe"))


@pytest.fixture
def regbase():
    import winreg
    base = rf"Software\TDownloadTest\{uuid.uuid4().hex}"
    yield winreg.HKEY_CURRENT_USER, base
    I.delete_tree(winreg.HKEY_CURRENT_USER, r"Software\TDownloadTest")
    with pytest.raises(FileNotFoundError):
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\TDownloadTest")


@win_only
def test_register_protocol_on_temp_key(regbase):
    import winreg
    root, base = regbase
    classes = base + r"\Classes"
    assert I.protocol_command(root=root, base=classes) is None
    I.register_protocol(command='"C:\\Đường dẫn\\TDownload.exe" "%1"', icon="", root=root, base=classes)
    assert I.protocol_command(root=root, base=classes) == '"C:\\Đường dẫn\\TDownload.exe" "%1"'
    with winreg.OpenKey(root, classes + r"\tdownload") as k:
        assert winreg.QueryValueEx(k, "URL Protocol")[0] == ""
        assert winreg.QueryValueEx(k, None)[0] == "URL:TDownload"
    I.unregister_protocol(root=root, base=classes)
    assert I.protocol_command(root=root, base=classes) is None
    I.unregister_protocol(root=root, base=classes)          # gỡ lần 2 không lỗi


@win_only
def test_autostart_on_temp_key(regbase):
    root, base = regbase
    run = base + r"\Run"
    I.set_autostart(True, root=root, key=run)
    assert I.autostart_command(root=root, key=run) == I.app_command("--minimized")
    I.set_autostart(False, root=root, key=run)
    assert I.autostart_command(root=root, key=run) is None
    I.set_autostart(False, root=root, key=run)               # tắt lần 2 không lỗi


@win_only
def test_sync_only_touches_enabled_options(regbase):
    root, base = regbase
    classes, run = base + r"\Classes", base + r"\Run"
    s = Settings()
    I.sync(s, root=root, base=classes, run_key=run)         # mặc định tắt → không ghi gì
    assert I.protocol_command(root=root, base=classes) is None
    assert I.autostart_command(root=root, key=run) is None
    I.register_protocol(command='"D:\\cu\\TDownload.exe" "%1"', root=root, base=classes)
    s.browser_protocol = s.autostart = True
    I.sync(s, root=root, base=classes, run_key=run)         # app đã chuyển chỗ → lệnh được ghi lại
    assert I.protocol_command(root=root, base=classes) == I.app_command('"%1"')
    assert I.autostart_command(root=root, key=run) == I.app_command("--minimized")


def test_browser_link_kept_until_ui_ready(engine):
    """Extension mở app rồi gửi link ngay: API nhận trước khi cửa sổ nối sự kiện → không được mất link."""
    events = []
    engine.ui_attached = True
    engine.listeners.append(lambda k, p: events.append((k, p.get("url"))) if k == "browser_add" else None)
    engine.call_sync(engine.handle_browser_add, {"url": "https://h.vn/a.zip"})
    assert events == []
    engine.call_sync(engine.ui_ready)
    assert events == [("browser_add", "https://h.vn/a.zip")]
    engine.call_sync(engine.handle_browser_add, {"url": "https://h.vn/b.zip"})
    assert events[-1] == ("browser_add", "https://h.vn/b.zip")


@pytest.mark.skipif(shutil.which("node") is None, reason="cần Node.js")
def test_extension_falls_back_when_app_missing():
    """Chạy background.js thật với API chrome giả: menu chuột phải khi app tắt."""
    r = subprocess.run(["node", os.path.join("tests", "ext_harness.mjs")], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", timeout=90)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "7/7" in r.stdout

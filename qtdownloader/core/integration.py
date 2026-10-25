"""Tích hợp Windows (chỉ khi người dùng bật trong Tuỳ chọn): giao thức qtdownloader:// và khởi động cùng Windows.

Giao thức để extension mở app khi app chưa chạy:
  * ``qtdownloader://open``                          — mở cửa sổ chính
  * ``qtdownloader://open?minimized=1``              — chỉ khởi động (xuống khay)
  * ``qtdownloader://add?url=<mã hoá>&referer=…&filename=…`` — mở hộp thoại thêm link (luôn hỏi người dùng)

Mọi hàm ghi registry nhận ``root``/đường dẫn khoá để test chạy trên một khoá con tạm, không đụng khoá thật.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

PROTOCOL = "qtdownloader"
CLASSES_KEY = r"Software\Classes"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "QTDownloader"
# Tên cũ (TDownload ≤ 1.0.3): link cũ vẫn mở được app; khoá registry cũ được gỡ khi mở bản mới (sync)
LEGACY_PROTOCOL = "tdownload"
LEGACY_RUN_VALUE = "TDownload"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================ đối số dòng lệnh
@dataclass
class LaunchArgs:
    adds: list[dict] = field(default_factory=list)   # {"url", "referer"?, "filename"?, "from_protocol"?}
    minimized: bool = False


def parse_protocol_url(text: str) -> dict | None:
    """``qtdownloader://…`` → {"action": "open"|"add", …}; None nếu không phải link hợp lệ."""
    if not text.lower().startswith((PROTOCOL + ":", LEGACY_PROTOCOL + ":")):
        return None
    parts = urlsplit(text)
    # qtdownloader://add?… · qtdownloader://add/?… · qtdownloader:add?… (và tdownload://… của bản cũ) đều được
    action = (parts.netloc or parts.path).strip("/").lower()
    q = {k: v[0] for k, v in parse_qs(parts.query).items() if v}
    minimized = q.get("minimized", "") in ("1", "true", "yes")
    if action in ("", "open"):
        return {"action": "open", "minimized": minimized}
    if action == "add":
        url = q.get("url", "").strip()
        if not url.lower().startswith(("http://", "https://")):
            return None
        out = {"action": "add", "url": url, "minimized": minimized}
        for k in ("referer", "filename"):
            if q.get(k):
                out[k] = q[k]
        return out
    return None


def parse_launch_args(args: list[str]) -> LaunchArgs:
    """Đối số khi chạy app: URL http(s) thường, link qtdownloader://, ``--minimized``."""
    res = LaunchArgs(minimized="--minimized" in args)
    for a in args:
        if a.lower().startswith(("http://", "https://")):
            res.adds.append({"url": a})
            continue
        p = parse_protocol_url(a)
        if p is None:
            continue
        res.minimized = res.minimized or p["minimized"]
        if p["action"] == "add":
            res.adds.append({k: v for k, v in p.items() if k in ("url", "referer", "filename")}
                            | {"from_protocol": True})
    return res


# ============================================================================ lệnh khởi chạy app
def app_command(*extra: str) -> str:
    """Dòng lệnh mở lại chính bản app đang chạy (exe đóng gói, hoặc pythonw + mã nguồn)."""
    if getattr(sys, "frozen", False):
        parts = [sys.executable]
    else:
        exe = sys.executable
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.basename(exe).lower() == "python.exe" and os.path.exists(w):
            exe = w
        script = os.path.join(ROOT_DIR, "run_qtdownloader.py")
        # trình duyệt chạy lệnh với thư mục làm việc bất kỳ → dùng đường dẫn tuyệt đối tới script
        parts = [exe, script] if os.path.exists(script) else [exe, "-m", "qtdownloader"]
    return " ".join([f'"{p}"' for p in parts] + list(extra))


def app_icon() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}",0'
    ico = os.path.join(ROOT_DIR, "assets", "qtdownloader.ico")
    return f'"{ico}"' if os.path.exists(ico) else ""


# ============================================================================ registry
def _winreg():
    import winreg  # chỉ có trên Windows
    return winreg


def _root(root):
    return _winreg().HKEY_CURRENT_USER if root is None else root


def _set(root, path: str, name: str | None, value: str) -> None:
    wr = _winreg()
    with wr.CreateKeyEx(root, path, 0, wr.KEY_WRITE) as k:
        wr.SetValueEx(k, name, 0, wr.REG_SZ, value)


def _get(root, path: str, name: str | None) -> str | None:
    wr = _winreg()
    try:
        with wr.OpenKey(root, path, 0, wr.KEY_READ) as k:
            return wr.QueryValueEx(k, name)[0]
    except OSError:
        return None


def delete_tree(root, path: str) -> None:
    """Xoá khoá và mọi khoá con (winreg không có RegDeleteTree)."""
    wr = _winreg()
    try:
        with wr.OpenKey(root, path, 0, wr.KEY_READ | wr.KEY_WRITE) as k:
            while True:
                try:
                    sub = wr.EnumKey(k, 0)
                except OSError:
                    break
                delete_tree(root, path + "\\" + sub)
        wr.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def register_protocol(command: str | None = None, icon: str | None = None, *, root=None,
                      base: str = CLASSES_KEY) -> None:
    """HKCU\\Software\\Classes\\qtdownloader → app_command() "%1". Chỉ gọi khi người dùng bật tuỳ chọn."""
    r = _root(root)
    key = f"{base}\\{PROTOCOL}"
    _set(r, key, None, "URL:QT Downloader")
    _set(r, key, "URL Protocol", "")
    icon = app_icon() if icon is None else icon
    if icon:
        _set(r, key + r"\DefaultIcon", None, icon)
    _set(r, key + r"\shell\open", "FriendlyAppName", "QT Downloader")
    _set(r, key + r"\shell\open\command", None, command or app_command('"%1"'))


def unregister_protocol(*, root=None, base: str = CLASSES_KEY) -> None:
    delete_tree(_root(root), f"{base}\\{PROTOCOL}")


def protocol_command(*, root=None, base: str = CLASSES_KEY) -> str | None:
    return _get(_root(root), f"{base}\\{PROTOCOL}\\shell\\open\\command", None)


def _delete_value(root, key: str, name: str) -> None:
    wr = _winreg()
    try:
        with wr.OpenKey(root, key, 0, wr.KEY_SET_VALUE) as k:
            wr.DeleteValue(k, name)
    except FileNotFoundError:
        pass


def set_autostart(enabled: bool, command: str | None = None, *, root=None, key: str = RUN_KEY) -> None:
    """Khởi động cùng Windows, thu nhỏ xuống khay. Chỉ gọi khi người dùng bật tuỳ chọn."""
    r = _root(root)
    if enabled:
        _set(r, key, RUN_VALUE, command or app_command("--minimized"))
    else:
        _delete_value(r, key, RUN_VALUE)


def autostart_command(*, root=None, key: str = RUN_KEY) -> str | None:
    return _get(_root(root), key, RUN_VALUE)


def remove_legacy(*, root=None, base: str = CLASSES_KEY, run_key: str = RUN_KEY) -> None:
    """Gỡ khoá do bản TDownload cũ ghi: giao thức tdownload:// và mục khởi động "TDownload" (trỏ tới exe cũ —
    để lại thì Windows mở cả bản cũ lẫn bản mới khi đăng nhập). Tuỳ chọn đang bật thì sync() ghi lại tên mới."""
    r = _root(root)
    delete_tree(r, f"{base}\\{LEGACY_PROTOCOL}")
    _delete_value(r, run_key, LEGACY_RUN_VALUE)


def sync(settings, *, root=None, base: str = CLASSES_KEY, run_key: str = RUN_KEY) -> None:
    """Lúc mở app: tuỳ chọn đang bật mà lệnh trong registry cũ (đã chuyển thư mục app) thì ghi lại.

    Tuỳ chọn tắt thì không đụng tới registry.
    """
    if sys.platform != "win32":
        return
    remove_legacy(root=root, base=base, run_key=run_key)
    if settings.browser_protocol and protocol_command(root=root, base=base) != app_command('"%1"'):
        register_protocol(root=root, base=base)
    if settings.autostart and autostart_command(root=root, key=run_key) != app_command("--minimized"):
        set_autostart(True, root=root, key=run_key)

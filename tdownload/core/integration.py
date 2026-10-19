"""Tích hợp Windows (chỉ khi người dùng bật trong Tuỳ chọn): giao thức tdownload:// và khởi động cùng Windows.

Giao thức để extension mở app khi app chưa chạy:
  * ``tdownload://open``                          — mở cửa sổ chính
  * ``tdownload://open?minimized=1``              — chỉ khởi động (xuống khay)
  * ``tdownload://add?url=<mã hoá>&referer=…&filename=…`` — mở hộp thoại thêm link (luôn hỏi người dùng)

Mọi hàm ghi registry nhận ``root``/đường dẫn khoá để test chạy trên một khoá con tạm, không đụng khoá thật.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

PROTOCOL = "tdownload"
CLASSES_KEY = r"Software\Classes"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "TDownload"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================ đối số dòng lệnh
@dataclass
class LaunchArgs:
    adds: list[dict] = field(default_factory=list)   # {"url", "referer"?, "filename"?, "from_protocol"?}
    minimized: bool = False


def parse_protocol_url(text: str) -> dict | None:
    """``tdownload://…`` → {"action": "open"|"add", …}; None nếu không phải link hợp lệ."""
    if not text.lower().startswith(PROTOCOL + ":"):
        return None
    parts = urlsplit(text)
    # tdownload://add?… · tdownload://add/?… · tdownload:add?… đều được
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
    """Đối số khi chạy app: URL http(s) thường, link tdownload://, ``--minimized``."""
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
        script = os.path.join(ROOT_DIR, "run_tdownload.py")
        # trình duyệt chạy lệnh với thư mục làm việc bất kỳ → dùng đường dẫn tuyệt đối tới script
        parts = [exe, script] if os.path.exists(script) else [exe, "-m", "tdownload"]
    return " ".join([f'"{p}"' for p in parts] + list(extra))


def app_icon() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}",0'
    ico = os.path.join(ROOT_DIR, "assets", "tdownload.ico")
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
    """HKCU\\Software\\Classes\\tdownload → app_command() "%1". Chỉ gọi khi người dùng bật tuỳ chọn."""
    r = _root(root)
    key = f"{base}\\{PROTOCOL}"
    _set(r, key, None, "URL:TDownload")
    _set(r, key, "URL Protocol", "")
    icon = app_icon() if icon is None else icon
    if icon:
        _set(r, key + r"\DefaultIcon", None, icon)
    _set(r, key + r"\shell\open", "FriendlyAppName", "TDownload")
    _set(r, key + r"\shell\open\command", None, command or app_command('"%1"'))


def unregister_protocol(*, root=None, base: str = CLASSES_KEY) -> None:
    delete_tree(_root(root), f"{base}\\{PROTOCOL}")


def protocol_command(*, root=None, base: str = CLASSES_KEY) -> str | None:
    return _get(_root(root), f"{base}\\{PROTOCOL}\\shell\\open\\command", None)


def set_autostart(enabled: bool, command: str | None = None, *, root=None, key: str = RUN_KEY) -> None:
    """Khởi động cùng Windows, thu nhỏ xuống khay. Chỉ gọi khi người dùng bật tuỳ chọn."""
    wr = _winreg()
    r = _root(root)
    if enabled:
        _set(r, key, RUN_VALUE, command or app_command("--minimized"))
        return
    try:
        with wr.OpenKey(r, key, 0, wr.KEY_SET_VALUE) as k:
            wr.DeleteValue(k, RUN_VALUE)
    except FileNotFoundError:
        pass


def autostart_command(*, root=None, key: str = RUN_KEY) -> str | None:
    return _get(_root(root), key, RUN_VALUE)


def sync(settings, *, root=None, base: str = CLASSES_KEY, run_key: str = RUN_KEY) -> None:
    """Lúc mở app: tuỳ chọn đang bật mà lệnh trong registry cũ (đã chuyển thư mục app) thì ghi lại.

    Tuỳ chọn tắt thì không đụng tới registry.
    """
    if sys.platform != "win32":
        return
    if settings.browser_protocol and protocol_command(root=root, base=base) != app_command('"%1"'):
        register_protocol(root=root, base=base)
    if settings.autostart and autostart_command(root=root, key=run_key) != app_command("--minimized"):
        set_autostart(True, root=root, key=run_key)

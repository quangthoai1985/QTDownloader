"""Khởi chạy giao diện: 1 phiên bản duy nhất, engine nền, khay hệ thống."""

from __future__ import annotations

import getpass
import hashlib
import json
import logging
import logging.handlers
import os
import subprocess
import sys

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import APP_ID, APP_MUTEX_NAME, APP_NAME
from ..core import integration
from ..core.engine import Engine
from ..core.settings import resolve_data_dir
from . import icons
from .bridge import Bridge
from .main_window import MainWindow


def server_name(data_dir: str) -> str:
    """Mỗi thư mục dữ liệu là một "phiên bản" riêng → bản thử nghiệm (QTDOWNLOADER_DATA) không đụng app đang dùng."""
    user = "".join(c for c in getpass.getuser() if c.isalnum())
    tag = hashlib.sha1(os.path.normcase(os.path.abspath(data_dir)).encode("utf-8")).hexdigest()[:8]
    return f"{APP_ID}-{user}-{tag}"


def _create_app_mutex():
    """Mutex có tên để bộ cài / trình gỡ cài đặt (Inno Setup: AppMutex) biết app đang mở và đề nghị đóng lại."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        return ctypes.windll.kernel32.CreateMutexW(None, False, APP_MUTEX_NAME) or None
    except (AttributeError, OSError):
        return None


def _close_app_mutex(handle) -> None:
    if handle:
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(handle)
        except (AttributeError, OSError):
            pass


def _setup_logging(data_dir) -> None:
    log_dir = os.path.join(data_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(os.path.join(log_dir, "qtdownloader.log"), maxBytes=2_000_000,
                                             backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(h)


def _send_to_running(name: str, adds: list[dict], show: bool) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(400):
        return False
    sock.write(json.dumps({"adds": adds, "show": show}).encode())
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    launch = integration.parse_launch_args(argv[1:])   # http(s)://…, qtdownloader://…, --minimized
    minimized = launch.minimized
    if sys.platform == "win32":
        try:  # taskbar hiện icon QT Downloader thay vì icon Python
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("QTDownloader.App")
        except (AttributeError, OSError):
            pass
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(icons.app_icon())
    app.setQuitOnLastWindowClosed(False)

    data_dir = str(resolve_data_dir())
    name = server_name(data_dir)
    if _send_to_running(name, launch.adds, not minimized):
        return 0
    server = QLocalServer()
    QLocalServer.removeServer(name)
    server.listen(name)
    mutex = _create_app_mutex()
    _setup_logging(data_dir)
    try:
        engine = Engine(data_dir)
        engine.ui_attached = True
        engine.start()
    except Exception as e:  # noqa: BLE001
        QMessageBox.critical(None, APP_NAME, f"Không khởi động được engine:\n{e}")
        return 1
    try:  # tuỳ chọn qtdownloader:// / khởi động cùng Windows đang bật → cập nhật đường dẫn nếu app đã chuyển chỗ
        integration.sync(engine.settings)
    except OSError:
        logging.getLogger("qtdownloader").exception("Không cập nhật được registry")
    bridge = Bridge(engine)
    win = MainWindow(bridge)

    def open_add(a: dict) -> None:
        if a.get("from_protocol"):   # từ qtdownloader://add → hộp thoại nổi trên cùng như link từ extension
            win.show_add_dialog(a["url"], {k: v for k, v in a.items() if k != "from_protocol"})
        else:
            win.show_add_dialog(a["url"])

    def on_conn():
        while server.hasPendingConnections():
            c = server.nextPendingConnection()
            buf = bytearray()

            def read(c=c, buf=buf):
                buf.extend(bytes(c.readAll()))
                try:
                    data = json.loads(buf.decode() or "{}")
                except ValueError:
                    return            # chưa nhận đủ
                buf.clear()
                adds = data.get("adds") or [{"url": u} for u in data.get("urls", [])]
                if data.get("show", True):
                    win.show_window()
                for a in adds:
                    if str(a.get("url", "")).lower().startswith(("http://", "https://")):
                        open_add(a)
            c.readyRead.connect(read)

    server.newConnection.connect(on_conn)
    if not minimized:
        win.show()
    for a in launch.adds:
        QTimer.singleShot(300, lambda a=a: open_add(a))
    bridge.run(engine.ui_ready)   # cửa sổ đã nối sự kiện → nhận cả link extension gửi trong lúc app đang mở
    bridge.run(engine.startup_update, on_done=win.on_startup_update)   # hỏi GitHub mỗi lần mở (như QT PDF Pro)
    app.aboutToQuit.connect(engine.shutdown)
    rc = app.exec()
    server.close()
    _close_app_mutex(mutex)
    if win.run_after_exit:   # bộ cài bản mới: chạy sau khi engine đã tắt và mutex đã nhả
        try:
            subprocess.Popen(win.run_after_exit, close_fds=True,
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        except OSError:
            logging.getLogger("qtdownloader").exception("Không chạy được bộ cài bản mới")
    return rc

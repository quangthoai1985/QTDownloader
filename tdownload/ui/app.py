"""Khởi chạy giao diện: 1 phiên bản duy nhất, engine nền, khay hệ thống."""

from __future__ import annotations

import getpass
import hashlib
import json
import logging
import logging.handlers
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from ..core import integration
from ..core.engine import Engine
from ..core.settings import default_data_dir
from . import icons
from .bridge import Bridge
from .main_window import MainWindow


def server_name(data_dir: str) -> str:
    """Mỗi thư mục dữ liệu là một "phiên bản" riêng → bản thử nghiệm (TDOWNLOAD_DATA) không đụng app đang dùng."""
    user = "".join(c for c in getpass.getuser() if c.isalnum())
    tag = hashlib.sha1(os.path.normcase(os.path.abspath(data_dir)).encode("utf-8")).hexdigest()[:8]
    return f"TDownload-{user}-{tag}"


def _setup_logging(data_dir) -> None:
    log_dir = os.path.join(data_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(os.path.join(log_dir, "tdownload.log"), maxBytes=2_000_000,
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
    launch = integration.parse_launch_args(argv[1:])   # http(s)://…, tdownload://…, --minimized
    minimized = launch.minimized
    if sys.platform == "win32":
        try:  # taskbar hiện icon TDownload thay vì icon Python
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TDownload.App")
        except (AttributeError, OSError):
            pass
    app = QApplication(argv)
    app.setApplicationName("TDownload")
    app.setOrganizationName("TDownload")
    app.setWindowIcon(icons.app_icon())
    app.setQuitOnLastWindowClosed(False)

    data_dir = os.environ.get("TDOWNLOAD_DATA") or str(default_data_dir())
    name = server_name(data_dir)
    if _send_to_running(name, launch.adds, not minimized):
        return 0
    server = QLocalServer()
    QLocalServer.removeServer(name)
    server.listen(name)
    _setup_logging(data_dir)
    try:
        engine = Engine(data_dir)
        engine.ui_attached = True
        engine.start()
    except Exception as e:  # noqa: BLE001
        QMessageBox.critical(None, "TDownload", f"Không khởi động được engine:\n{e}")
        return 1
    try:  # tuỳ chọn tdownload:// / khởi động cùng Windows đang bật → cập nhật đường dẫn nếu app đã chuyển chỗ
        integration.sync(engine.settings)
    except OSError:
        logging.getLogger("tdownload").exception("Không cập nhật được registry")
    bridge = Bridge(engine)
    win = MainWindow(bridge)

    def open_add(a: dict) -> None:
        if a.get("from_protocol"):   # từ tdownload://add → hộp thoại nổi trên cùng như link từ extension
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
    app.aboutToQuit.connect(engine.shutdown)
    return app.exec()

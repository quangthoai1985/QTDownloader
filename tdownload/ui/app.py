"""Khởi chạy giao diện: 1 phiên bản duy nhất, engine nền, khay hệ thống."""

from __future__ import annotations

import getpass
import json
import logging
import logging.handlers
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from ..core.engine import Engine
from ..core.settings import default_data_dir
from . import icons
from .bridge import Bridge
from .main_window import MainWindow

SERVER_NAME = "TDownload-" + "".join(c for c in getpass.getuser() if c.isalnum())


def _setup_logging(data_dir) -> None:
    log_dir = os.path.join(data_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(os.path.join(log_dir, "tdownload.log"), maxBytes=2_000_000,
                                             backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(h)


def _send_to_running(urls: list[str]) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(400):
        return False
    sock.write(json.dumps({"urls": urls}).encode())
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    urls = [a for a in argv[1:] if a.lower().startswith(("http://", "https://"))]
    minimized = "--minimized" in argv
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

    if _send_to_running(urls):
        return 0
    server = QLocalServer()
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    data_dir = os.environ.get("TDOWNLOAD_DATA") or str(default_data_dir())
    _setup_logging(data_dir)
    try:
        engine = Engine(data_dir)
        engine.ui_attached = True
        engine.start()
    except Exception as e:  # noqa: BLE001
        QMessageBox.critical(None, "TDownload", f"Không khởi động được engine:\n{e}")
        return 1
    bridge = Bridge(engine)
    win = MainWindow(bridge)

    def on_conn():
        while server.hasPendingConnections():
            c = server.nextPendingConnection()

            def read(c=c):
                try:
                    data = json.loads(bytes(c.readAll()).decode() or "{}")
                except ValueError:
                    data = {}
                win.show_window()
                for u in data.get("urls", []):
                    win.show_add_dialog(u)
            c.readyRead.connect(read)

    server.newConnection.connect(on_conn)
    if not minimized:
        win.show()
    for u in urls:
        QTimer.singleShot(300, lambda u=u: win.show_add_dialog(u))
    app.aboutToQuit.connect(engine.shutdown)
    return app.exec()

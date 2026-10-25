"""Sinh icon PNG cho extension và qtdownloader.ico cho bản build từ hình SVG của app."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtGui import QGuiApplication, QIcon  # noqa: E402

from qtdownloader.ui.icons import app_pixmap  # noqa: E402

app = QGuiApplication(sys.argv)
ext_dir = os.path.join(ROOT, "extension", "icons")
os.makedirs(ext_dir, exist_ok=True)
for s in (16, 32, 48, 128):
    app_pixmap(s).save(os.path.join(ext_dir, f"{s}.png"))
assets = os.path.join(ROOT, "assets")
os.makedirs(assets, exist_ok=True)
app_pixmap(256).save(os.path.join(assets, "qtdownloader.ico"))
app_pixmap(256).save(os.path.join(assets, "qtdownloader.png"))
print("icons ->", ext_dir, "|", assets)

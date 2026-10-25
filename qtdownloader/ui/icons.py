"""Bộ icon vẽ bằng SVG nội tuyến (tự thiết kế), tự đổi màu theo sáng/tối."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QFileInfo, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QFileIconProvider

ACCENT = "#2563eb"
GREEN = "#16a34a"
RED = "#dc2626"
AMBER = "#d97706"

_S = 'fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
_A = 'fill="none" stroke="{a}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"'

PATHS = {
    "add": f'<rect x="3" y="3" width="18" height="18" rx="4" {_S}/><path d="M12 8v8M8 12h8" {_A}/>',
    "resume": f'<circle cx="12" cy="12" r="9" {_S}/><path d="M10 8.5v7l6-3.5z" fill="{{a}}" stroke="{{a}}" '
              f'stroke-width="1.5" stroke-linejoin="round"/>',
    "pause": f'<circle cx="12" cy="12" r="9" {_S}/><path d="M10 9v6M14 9v6" {_A}/>',
    "stop_all": f'<circle cx="12" cy="12" r="9" {_S}/><rect x="9" y="9" width="6" height="6" rx="1" '
                f'fill="{{r}}" stroke="{{r}}" stroke-width="1"/>',
    "delete": f'<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" {_S}/>',
    "clean": f'<path d="M4 6h10M4 12h7M4 18h6" {_S}/><path d="M15 15l5 5M20 15l-5 5" {_A}/>',
    "settings": f'<circle cx="12" cy="12" r="3.2" {_A}/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3'
                f'M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1" {_S}/>',
    "schedule": f'<circle cx="12" cy="12" r="9" {_S}/><path d="M12 7v5l3.5 2" {_A}/>',
    "queue_start": f'<path d="M4 6h9M4 12h9M4 18h6" {_S}/><path d="M15 13v7l6-3.5z" fill="{{a}}" '
                   f'stroke="{{a}}" stroke-width="1.5" stroke-linejoin="round"/>',
    "queue_stop": f'<path d="M4 6h9M4 12h9M4 18h6" {_S}/><path d="M16 13v7M20 13v7" {_A}/>',
    "batch": f'<rect x="7" y="3" width="13" height="15" rx="2" {_S}/><path d="M4 7v11a3 3 0 0 0 3 3h9" {_S}/>'
             f'<path d="M10.5 8h6M10.5 11.5h6M10.5 15h3.5" {_A}/>',
    "folder": f'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" {_S}/>',
    "open": f'<path d="M14 4h6v6M20 4l-9 9" {_A}/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 '
            f'1-1h5" {_S}/>',
    "restart": f'<path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4" {_S}/>',
    "link": f'<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 '
            f'5.7 5.7l1-1" {_S}/>',
    "speed": f'<path d="M4 18a8 8 0 1 1 16 0" {_S}/><path d="M12 18l4-6" {_A}/>',
    "all": f'<path d="M12 3v11M7.5 9.5L12 14l4.5-4.5" {_A}/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" '
           f'{_S}/>',
    "unfinished": f'<circle cx="12" cy="12" r="9" {_S}/><path d="M12 3a9 9 0 0 1 9 9h-9z" fill="{{a}}" '
                  f'stroke="none"/>',
    "finished": f'<circle cx="12" cy="12" r="9" {_S}/><path d="M8 12.5l2.8 2.8L16.5 9.5" '
                f'fill="none" stroke="{{g}}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
    "queue": f'<path d="M4 6h16M4 12h16M4 18h10" {_S}/>',
    "compressed": f'<rect x="5" y="3" width="14" height="18" rx="2" {_S}/><path d="M12 3v2M12 7v2M12 11v2" '
                  f'{_A}/><rect x="10" y="14" width="4" height="4" rx="1" {_A}/>',
    "documents": f'<path d="M6 3h8l4 4v14H6z" {_S}/><path d="M14 3v4h4M9 12h6M9 16h6" {_A}/>',
    "music": f'<path d="M9 18V6l10-2v12" {_S}/><circle cx="7" cy="18" r="2.5" {_A}/>'
             f'<circle cx="17" cy="16" r="2.5" {_A}/>',
    "programs": f'<rect x="3" y="4" width="18" height="14" rx="2" {_S}/><path d="M7 21h10M7 9l3 2.5L7 14" {_A}/>',
    "video": f'<rect x="3" y="6" width="13" height="12" rx="2" {_S}/><path d="M16 10.5l5-3v9l-5-3" {_A}/>',
    "general": f'<path d="M6 3h8l4 4v14H6z" {_S}/><path d="M14 3v4h4" {_S}/>',
    "info": f'<circle cx="12" cy="12" r="9" {_S}/><path d="M12 11v6M12 7.5v.5" {_A}/>',
    "globe": f'<circle cx="12" cy="12" r="9" {_S}/><path d="M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 '
             f'14.5 0 18" {_S}/>',
}


def _palette_text() -> str:
    app = QApplication.instance()
    if app is None:
        return "#1f2937"
    return app.palette().color(QPalette.ColorRole.WindowText).name()


def _svg(name: str, color: str) -> bytes:
    body = PATHS[name].format(c=color, a=ACCENT, r=RED, g=GREEN)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'.encode()


def _render(svg: bytes, size: int) -> QPixmap:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg)).render(p, QRectF(0, 0, size, size))
    p.end()
    return QPixmap.fromImage(img)


@lru_cache(maxsize=None)
def _icon_cached(name: str, color: str) -> QIcon:
    icon = QIcon()
    data = _svg(name, color)
    for s in (16, 20, 24, 32, 48):
        icon.addPixmap(_render(data, s))
    disabled = _svg(name, "#9ca3af").replace(ACCENT.encode(), b"#9ca3af").replace(RED.encode(), b"#9ca3af")
    for s in (16, 24, 32, 48):
        icon.addPixmap(_render(disabled, s), QIcon.Mode.Disabled)
    return icon


def icon(name: str) -> QIcon:
    return _icon_cached(name, _palette_text())


def clear_cache() -> None:
    _icon_cached.cache_clear()


APP_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#3b82f6"/><stop offset="1" stop-color="#1d4ed8"/></linearGradient></defs>'
    '<rect x="4" y="4" width="56" height="56" rx="14" fill="url(#g)"/>'
    '<path d="M32 14v24M21 28l11 11 11-11" fill="none" stroke="#fff" stroke-width="6" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M18 47h28" stroke="#bfdbfe" stroke-width="5" stroke-linecap="round"/>'
    '</svg>'
).encode()


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_render(APP_SVG, s))
    return icon


def app_pixmap(size: int) -> QPixmap:
    return _render(APP_SVG, size)


def tray_icon(active: bool) -> QIcon:
    if not active:
        return app_icon()
    pm = _render(APP_SVG, 32)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(GREEN))
    p.setPen(QColor("#ffffff"))
    p.drawEllipse(19, 19, 12, 12)
    p.end()
    return QIcon(pm)


_provider: QFileIconProvider | None = None


@lru_cache(maxsize=256)
def file_icon(ext: str) -> QIcon:
    global _provider
    if _provider is None:
        _provider = QFileIconProvider()
    return _provider.icon(QFileInfo(f"C:/__qtdownloader__/x{ext}"))

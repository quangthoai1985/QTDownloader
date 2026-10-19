"""Widget tự vẽ: thanh phân đoạn theo kết nối, đồ thị tốc độ, ô tiến trình trong bảng."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QWidget

from ..core.util import fmt_speed

# Màu cho từng kết nối (đủ tương phản trên nền sáng lẫn tối)
CONN_COLORS = ["#2563eb", "#0d9488", "#7c3aed", "#ea580c", "#db2777", "#16a34a", "#ca8a04", "#0891b2"]
DONE_COLOR = "#3b82f6"


def conn_color(wid: int | None) -> QColor:
    if not wid:
        return QColor(DONE_COLOR)
    return QColor(CONN_COLORS[(wid - 1) % len(CONN_COLORS)])


def is_dark(widget: QWidget) -> bool:
    return widget.palette().color(QPalette.ColorRole.Window).lightness() < 128


class SegmentBar(QWidget):
    """Thanh cho thấy tệp được chia thành những đoạn nào và kết nối nào đang tải đoạn nào."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.size_total = 0
        self.segments: list = []
        self.setMinimumHeight(22)

    def sizeHint(self) -> QSize:
        return QSize(400, 24)

    def set_data(self, size: int, segments: list) -> None:
        self.size_total = size
        self.segments = segments
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        dark = is_dark(self)
        bg = QColor("#1f2937") if dark else QColor("#e5e7eb")
        path = QPainterPath()
        path.addRoundedRect(r, 5, 5)
        p.setClipPath(path)
        p.fillRect(r, bg)
        total = self.size_total
        if total > 0:
            w = r.width()
            for seg in self.segments:
                start, end, pos, wid = seg[0], seg[1], seg[2], seg[3] if len(seg) > 3 else None
                if pos > start:
                    x0 = r.left() + w * start / total
                    x1 = r.left() + w * pos / total
                    c = conn_color(wid) if wid else QColor(DONE_COLOR)
                    if not wid:
                        c.setAlpha(170)
                    p.fillRect(QRectF(x0, r.top(), max(1.0, x1 - x0), r.height()), c)
                if wid and pos < end:  # con trỏ đầu ghi của kết nối
                    x = r.left() + w * pos / total
                    p.fillRect(QRectF(x - 1, r.top(), 2, r.height()), QColor("#ffffff" if dark else "#111827"))
            pen = QPen(QColor("#111827" if not dark else "#f9fafb"))
            pen.setWidthF(1)
            pen.setColor(QColor(0, 0, 0, 60) if not dark else QColor(255, 255, 255, 60))
            p.setPen(pen)
            for seg in self.segments[1:]:
                x = r.left() + w * seg[0] / total
                p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        p.setClipping(False)
        p.setPen(QPen(QColor(0, 0, 0, 40) if not dark else QColor(255, 255, 255, 40)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 5, 5)


class SpeedGraph(QWidget):
    def __init__(self, parent=None, samples: int = 120):
        super().__init__(parent)
        self.data: deque[float] = deque(maxlen=samples)
        self.setMinimumHeight(70)

    def sizeHint(self) -> QSize:
        return QSize(400, 80)

    def push(self, v: float) -> None:
        self.data.append(max(0.0, v))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        dark = is_dark(self)
        p.setPen(QPen(QColor(255, 255, 255, 30) if dark else QColor(0, 0, 0, 25)))
        p.setBrush(QColor("#111827") if dark else QColor("#f9fafb"))
        p.drawRoundedRect(r, 6, 6)
        for k in (1, 2, 3):
            y = r.top() + r.height() * k / 4
            p.drawLine(QPointF(r.left() + 4, y), QPointF(r.right() - 4, y))
        if len(self.data) < 2:
            return
        peak = max(self.data) or 1.0
        n = self.data.maxlen
        step = r.width() / (n - 1)
        x0 = r.right() - step * (len(self.data) - 1)
        pts = [QPointF(x0 + i * step, r.bottom() - 4 - (r.height() - 18) * v / peak) for i, v in enumerate(self.data)]
        area = QPainterPath(QPointF(pts[0].x(), r.bottom()))
        for pt in pts:
            area.lineTo(pt)
        area.lineTo(QPointF(pts[-1].x(), r.bottom()))
        fill = QColor(DONE_COLOR)
        fill.setAlpha(60)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawPath(area)
        line = QPainterPath(pts[0])
        for pt in pts[1:]:
            line.lineTo(pt)
        pen = QPen(QColor(DONE_COLOR))
        pen.setWidthF(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line)
        p.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1))
        p.setFont(f)
        p.drawText(r.adjusted(8, 4, -8, -4), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                   f"đỉnh {fmt_speed(peak)}")


PROGRESS_ROLE = Qt.ItemDataRole.UserRole + 1


class ProgressDelegate(QStyledItemDelegate):
    """Vẽ thanh tiến trình mảnh + chữ trong cột Trạng thái."""

    COLORS = {"downloading": "#2563eb", "connecting": "#2563eb", "merging": "#7c3aed", "verifying": "#7c3aed",
              "paused": "#9ca3af", "queued": "#d97706", "error": "#dc2626", "completed": "#16a34a"}

    def paint(self, painter: QPainter, option, index):
        info = index.data(PROGRESS_ROLE)
        if not info:
            return super().paint(painter, option, index)
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else None
        if style:
            option.text = ""
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)
        progress, status, text = info
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect).adjusted(6, 4, -6, -4)
        color = QColor(self.COLORS.get(status, "#2563eb"))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if progress is not None and status not in ("completed",):
            bar = QRectF(r.left(), r.bottom() - 4, r.width(), 4)
            bg = QColor(color)
            bg.setAlpha(45)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(bar, 2, 2)
            done = QRectF(bar.left(), bar.top(), bar.width() * max(0.0, min(1.0, progress)), bar.height())
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(done, 2, 2)
            r = r.adjusted(0, -2, 0, -5)
        pal = option.palette
        tc = pal.color(QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text)
        if status in ("error", "completed", "queued") and not selected:
            tc = color
        painter.setPen(tc)
        painter.drawText(r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        painter.restore()

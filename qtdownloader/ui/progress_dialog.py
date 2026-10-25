"""Cửa sổ tiến trình của một tệp — hiển thị từng kết nối như IDM."""

from __future__ import annotations


from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ..core.util import fmt_eta, fmt_size, fmt_speed
from . import icons
from .bridge import Bridge
from .widgets import SegmentBar, SpeedGraph, conn_color


def _swatch(color: QColor) -> QPixmap:
    pm = QPixmap(12, 12)
    pm.fill(color)
    return pm


class ProgressDialog(QDialog):
    def __init__(self, bridge: Bridge, ident: str, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.ident = ident
        self.setWindowIcon(icons.app_icon())
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setMinimumWidth(640)

        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        st = QWidget()
        sl = QVBoxLayout(st)
        self.url_lbl = QLabel()
        self.url_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.url_lbl.setStyleSheet("color: palette(placeholder-text);")
        sl.addWidget(self.url_lbl)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        self.vals = {}
        rows = [("status", "Trạng thái"), ("size", "Kích thước"), ("done", "Đã tải"), ("speed", "Tốc độ"),
                ("eta", "Thời gian còn lại"), ("resume", "Tạm dừng/tải tiếp")]
        for i, (key, label) in enumerate(rows):
            r, c = divmod(i, 2)
            lb = QLabel(label + ":")
            lb.setStyleSheet("color: palette(placeholder-text);")
            v = QLabel("—")
            f = QFont(v.font())
            f.setBold(True)
            v.setFont(f)
            grid.addWidget(lb, r, c * 2)
            grid.addWidget(v, r, c * 2 + 1)
            self.vals[key] = v
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        sl.addLayout(grid)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        sl.addWidget(self.bar)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: #d97706;")
        self.message.hide()
        sl.addWidget(self.message)

        self.details = QWidget()
        dl = QVBoxLayout(self.details)
        dl.setContentsMargins(0, 0, 0, 0)
        cap = QLabel("Phân đoạn và kết nối")
        cap.setStyleSheet("font-weight:600;")
        dl.addWidget(cap)
        self.segbar = SegmentBar()
        dl.addWidget(self.segbar)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Đã tải", "Tốc độ", "Thông tin"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setFixedHeight(170)
        dl.addWidget(self.table)
        self.graph = SpeedGraph()
        dl.addWidget(self.graph)
        sl.addWidget(self.details)
        tabs.addTab(st, "Trạng thái tải")

        lim = QWidget()
        ll = QVBoxLayout(lim)
        self.lim_on = QCheckBox("Giới hạn tốc độ riêng cho tệp này")
        ll.addWidget(self.lim_on)
        row = QHBoxLayout()
        self.lim_val = QSpinBox()
        self.lim_val.setRange(1, 10_000_000)
        self.lim_val.setValue(500)
        self.lim_val.setSuffix(" KB/s")
        row.addWidget(self.lim_val)
        apply_b = QPushButton("Áp dụng")
        row.addWidget(apply_b)
        row.addStretch(1)
        ll.addLayout(row)
        ll.addWidget(QLabel("Hữu ích khi vừa tải vừa họp trực tuyến, chơi game… Có hiệu lực ngay, không cần dừng."))
        ll.addStretch(1)
        tabs.addTab(lim, "Giới hạn tốc độ")
        apply_b.clicked.connect(self._apply_limit)
        self.lim_on.toggled.connect(lambda _: self._apply_limit())

        opt = QWidget()
        ol = QVBoxLayout(opt)
        self.open_after = QCheckBox("Mở tệp khi tải xong")
        self.reveal_after = QCheckBox("Mở thư mục chứa tệp khi tải xong")
        self.no_dialog = QCheckBox("Không hiện hộp thoại 'Tải xong'")
        for cb in (self.open_after, self.reveal_after, self.no_dialog):
            ol.addWidget(cb)
        ol.addStretch(1)
        tabs.addTab(opt, "Khi tải xong")

        btns = QHBoxLayout()
        self.toggle_details = QPushButton("Ẩn chi tiết")
        self.toggle_details.clicked.connect(self._toggle_details)
        btns.addWidget(self.toggle_details)
        btns.addStretch(1)
        self.pause_btn = QPushButton(icons.icon("pause"), "Tạm dừng")
        self.pause_btn.clicked.connect(self._pause_resume)
        btns.addWidget(self.pause_btn)
        hide_b = QPushButton("Ẩn cửa sổ")
        hide_b.clicked.connect(self.hide)
        btns.addWidget(hide_b)
        lay.addLayout(btns)

        it = bridge.item(ident)
        if it and it.get("speed_limit_kb"):
            self.lim_on.blockSignals(True)
            self.lim_on.setChecked(True)
            self.lim_on.blockSignals(False)
            self.lim_val.setValue(it["speed_limit_kb"])
        self.refresh()

    def _toggle_details(self) -> None:
        vis = not self.details.isVisible()
        self.details.setVisible(vis)
        self.toggle_details.setText("Ẩn chi tiết" if vis else "Hiện chi tiết")
        self.adjustSize()

    def _apply_limit(self) -> None:
        kb = self.lim_val.value() if self.lim_on.isChecked() else 0
        self.bridge.run(self.bridge.engine.set_speed_limit, self.ident, kb)

    def _pause_resume(self) -> None:
        it = self.bridge.item(self.ident)
        if not it:
            return
        eng = self.bridge.engine
        self.bridge.run(eng.pause if it["active"] else eng.resume, self.ident)

    def refresh(self) -> None:
        it = self.bridge.item(self.ident)
        if it is None:
            self.close()
            return
        pct = it["progress"]
        title = f"{pct * 100:.0f}% {it['filename']}" if pct is not None and it["active"] else it["filename"]
        self.setWindowTitle(title)
        self.url_lbl.setText(it["url"] if len(it["url"]) < 110 else it["url"][:107] + "…")
        self.vals["status"].setText(it["status_text"] if it["status"] != "downloading" else "Đang nhận dữ liệu…")
        self.vals["size"].setText(fmt_size(it["size"]) if it["size"] >= 0 else "không rõ")
        done = fmt_size(it["downloaded"])
        if pct is not None:
            done += f"  ({pct * 100:.2f}%)"
        if it["kind"] == "hls" and it["hls"].get("total"):
            done += f"  · {it['hls']['done_count']}/{it['hls']['total']} đoạn video"
        self.vals["done"].setText(done)
        self.vals["speed"].setText(fmt_speed(it["speed"]) or "—")
        self.vals["eta"].setText(fmt_eta(it["eta"]) or "—")
        self.vals["resume"].setText({True: "Có", False: "Không"}.get(it["resumable"], "Chưa rõ"))
        self.bar.setValue(int((pct or 0) * 1000))
        msg = it["error"] or it["message"]
        self.message.setText(msg)
        self.message.setStyleSheet("color: #dc2626;" if it["error"] else "color: #d97706;")
        self.message.setVisible(bool(msg))
        self.segbar.set_data(it["size"], it["segments"])
        conns = it["conns"]
        self.table.setRowCount(len(conns))
        for r, c in enumerate(conns):
            num = QTableWidgetItem(str(c["wid"]))
            num.setIcon(_swatch(conn_color(c["wid"])))
            self.table.setItem(r, 0, num)
            self.table.setItem(r, 1, QTableWidgetItem(fmt_size(c["total"])))
            self.table.setItem(r, 2, QTableWidgetItem(fmt_speed(c["speed"])))
            self.table.setItem(r, 3, QTableWidgetItem(c["state"]))
        if it["active"]:
            self.graph.push(it["speed"])
        self.pause_btn.setText("Tạm dừng" if it["active"] else "Tiếp tục")
        self.pause_btn.setIcon(icons.icon("pause" if it["active"] else "resume"))
        self.pause_btn.setEnabled(it["status"] != "completed")

    def completion_options(self) -> tuple[bool, bool, bool]:
        """(mở tệp, mở thư mục, bỏ hộp thoại Tải xong) — cửa sổ chính xử lý khi tải xong."""
        return self.open_after.isChecked(), self.reveal_after.isChecked(), self.no_dialog.isChecked()

"""Các hộp thoại của QT Downloader."""

from __future__ import annotations

import os
import sys
from dataclasses import asdict

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QTabWidget, QTimeEdit, QToolButton, QVBoxLayout, QWidget,
)

from ..core import categories, integration
from ..core.util import expand_batch_pattern, filename_from_url, fmt_size, sanitize_filename
from . import icons
from .bridge import Bridge, open_path, reveal_path


def _muted(text: str = "") -> QLabel:
    lb = QLabel(text)
    lb.setWordWrap(True)
    lb.setStyleSheet("color: palette(placeholder-text);")
    return lb


def _dir_row(edit: QLineEdit, parent: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addWidget(edit, 1)
    b = QToolButton()
    b.setIcon(icons.icon("folder"))
    b.setToolTip("Chọn thư mục…")

    def pick():
        d = QFileDialog.getExistingDirectory(parent, "Chọn thư mục lưu", edit.text() or os.path.expanduser("~"))
        if d:
            edit.setText(os.path.normpath(d))
            edit.setModified(True)
            edit.editingFinished.emit()

    b.clicked.connect(pick)
    row.addWidget(b)
    return row


def vi_buttons(bb: QDialogButtonBox) -> QDialogButtonBox:
    """Qt không kèm bản dịch tiếng Việt → tự đặt chữ cho nút chuẩn."""
    names = {QDialogButtonBox.StandardButton.Ok: "Đồng ý", QDialogButtonBox.StandardButton.Cancel: "Huỷ",
             QDialogButtonBox.StandardButton.Close: "Đóng"}
    for std, text in names.items():
        b = bb.button(std)
        if b is not None:
            b.setText(text)
    return bb


def ask(parent, title: str, text: str, checkbox: str = "") -> tuple[bool, bool]:
    """Hộp hỏi Có/Không tiếng Việt; trả về (đồng ý, trạng thái ô đánh dấu)."""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(text)
    cb = None
    if checkbox:
        cb = QCheckBox(checkbox)
        box.setCheckBox(cb)
    yes = box.addButton("Có", QMessageBox.ButtonRole.YesRole)
    box.addButton("Không", QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(yes)
    box.exec()
    return box.clickedButton() is yes, bool(cb and cb.isChecked())


def default_dir_for(settings, category: str) -> str:
    base = settings.download_dir
    return os.path.join(base, categories.subdir(category)) if settings.use_category_dirs else base


# ============================================================================ Thêm URL
class AddUrlDialog(QDialog):
    """Tương đương hộp thoại "Download File Info" của IDM."""

    added = Signal(str, bool)   # id, bắt đầu ngay

    def __init__(self, bridge: Bridge, url: str = "", payload: dict | None = None, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.payload = payload or {}
        self.info: dict | None = None
        self._name_touched = False
        self._dir_touched = False
        self._cat_touched = False
        self.setWindowTitle("Thêm tệp tải xuống")
        self.setWindowIcon(icons.app_icon())
        self.setMinimumWidth(620)
        s = bridge.settings

        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.url = QLineEdit(url or self.payload.get("url", ""))
        self.url.setPlaceholderText("https://… (dán link tệp hoặc link .m3u8)")
        self.url.setClearButtonEnabled(True)
        top.addWidget(QLabel("Địa chỉ:"))
        top.addWidget(self.url, 1)
        self.check_btn = QPushButton("Kiểm tra")
        top.addWidget(self.check_btn)
        lay.addLayout(top)

        self.card = QFrame()
        self.card.setFrameShape(QFrame.Shape.StyledPanel)
        cl = QHBoxLayout(self.card)
        self.type_icon = QLabel()
        self.type_icon.setFixedSize(40, 40)
        cl.addWidget(self.type_icon)
        self.info_lbl = QLabel("Nhập địa chỉ rồi bấm Kiểm tra để xem thông tin tệp.")
        self.info_lbl.setWordWrap(True)
        self.info_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cl.addWidget(self.info_lbl, 1)
        lay.addWidget(self.card)
        self.warn = QLabel()
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet("color: #dc2626;")
        self.warn.hide()
        lay.addWidget(self.warn)

        form = QFormLayout()
        self.variant = QComboBox()
        self.variant_row = QLabel("Chất lượng:")
        form.addRow(self.variant_row, self.variant)
        self.variant.hide()
        self.variant_row.hide()
        self.name = QLineEdit(sanitize_filename(self.payload.get("filename", ""), "") or filename_from_url(self.url.text()))
        form.addRow("Lưu với tên:", self.name)
        row = QHBoxLayout()
        self.cat = QComboBox()
        for key in categories.ORDER:
            self.cat.addItem(icons.icon(key), categories.display_name(key), key)
        row.addWidget(self.cat, 1)
        row.addSpacing(12)
        row.addWidget(QLabel("Số kết nối:"))
        self.conns = QSpinBox()
        self.conns.setRange(1, 32)
        self.conns.setValue(s.max_connections)
        self.conns.setToolTip("IDM mặc định 8; tối đa 32. Server giới hạn thì QT Downloader tự giảm.")
        row.addWidget(self.conns)
        form.addRow("Phân loại:", row)
        self.dir = QLineEdit()
        form.addRow("Lưu vào:", _dir_row(self.dir, self))
        self.desc = QLineEdit()
        form.addRow("Mô tả:", self.desc)
        lay.addLayout(form)

        self.adv_btn = QToolButton()
        self.adv_btn.setText("Nâng cao")
        self.adv_btn.setCheckable(True)
        self.adv_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.adv_btn.setArrowType(Qt.ArrowType.RightArrow)
        lay.addWidget(self.adv_btn)
        self.adv = QGroupBox()
        af = QFormLayout(self.adv)
        self.referer = QLineEdit(self.payload.get("referer", ""))
        af.addRow("Referer:", self.referer)
        self.cookies = QLineEdit(self.payload.get("cookies", ""))
        self.cookies.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        af.addRow("Cookie:", self.cookies)
        self.mirrors = QPlainTextEdit()
        self.mirrors.setPlaceholderText("Mỗi dòng một link khác của CÙNG tệp — QT Downloader tải song song từ tất cả")
        self.mirrors.setFixedHeight(60)
        af.addRow("Nguồn phụ:", self.mirrors)
        self.checksum = QLineEdit()
        self.checksum.setPlaceholderText("sha256:… / md5:… (để trống: tự tìm tệp .sha256 cạnh link)")
        af.addRow("Checksum:", self.checksum)
        self.limit = QSpinBox()
        self.limit.setRange(0, 10_000_000)
        self.limit.setSuffix(" KB/s")
        self.limit.setSpecialValueText("Không giới hạn")
        af.addRow("Giới hạn tốc độ:", self.limit)
        self.adv.setVisible(False)
        lay.addWidget(self.adv)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.later_btn = QPushButton(icons.icon("queue"), "Tải sau")
        self.later_btn.setToolTip("Thêm vào hàng đợi, chưa tải")
        self.now_btn = QPushButton(icons.icon("all"), "Tải ngay")
        self.now_btn.setDefault(True)
        cancel = QPushButton("Huỷ")
        btns.addWidget(self.later_btn)
        btns.addWidget(self.now_btn)
        btns.addWidget(cancel)
        lay.addLayout(btns)

        self._timer = QTimer(self, singleShot=True, interval=700)
        self._timer.timeout.connect(self.check)
        self.url.textEdited.connect(lambda _: self._timer.start())
        self.check_btn.clicked.connect(self.check)
        self.name.textEdited.connect(self._on_name_edited)
        self.dir.textEdited.connect(lambda _: setattr(self, "_dir_touched", True))
        self.dir.editingFinished.connect(lambda: setattr(self, "_dir_touched", self.dir.isModified() or self._dir_touched))
        self.cat.activated.connect(self._on_cat_changed)
        self.adv_btn.toggled.connect(self._toggle_adv)
        self.now_btn.clicked.connect(lambda: self.submit(True))
        self.later_btn.clicked.connect(lambda: self.submit(False))
        cancel.clicked.connect(self.reject)
        self._apply_category(categories.category_for(self.name.text()))
        if self.url.text():
            QTimer.singleShot(0, self.check)

    def _toggle_adv(self, on: bool) -> None:
        self.adv.setVisible(on)
        self.adv_btn.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.adjustSize()

    def _on_name_edited(self, text: str) -> None:
        self._name_touched = True
        if not self._cat_touched:
            self._apply_category(categories.category_for(text))

    def _on_cat_changed(self, _i: int) -> None:
        self._cat_touched = True
        self._apply_category(self.cat.currentData(), from_user=True)

    def _apply_category(self, key: str, from_user: bool = False) -> None:
        if not from_user:
            self.cat.setCurrentIndex(max(0, self.cat.findData(key)))
        if not self._dir_touched:
            self.dir.setText(os.path.normpath(default_dir_for(self.bridge.settings, self.cat.currentData())))
        self.type_icon.setPixmap(icons.file_icon(os.path.splitext(self.name.text())[1].lower()).pixmap(40, 40))

    def check(self) -> None:
        url = self.url.text().strip()
        if not url.lower().startswith(("http://", "https://")):
            self.info_lbl.setText("Địa chỉ phải bắt đầu bằng http:// hoặc https://")
            return
        self.info_lbl.setText("Đang kiểm tra máy chủ…")
        self.warn.hide()
        self.check_btn.setEnabled(False)
        p = self.payload
        self.bridge.run(self.bridge.engine.probe_url, url, self.referer.text().strip(), self.cookies.text().strip(),
                        p.get("userAgent", ""), on_done=self._on_probe)

    def _on_probe(self, info, err) -> None:
        self.check_btn.setEnabled(True)
        if err is not None:
            self.info = None
            self.info_lbl.setText("Không lấy được thông tin tệp.")
            self.warn.setText(str(err))
            self.warn.show()
            return
        self.info = info
        if not self._name_touched and info.get("filename"):
            name = info["filename"]
            if self.payload.get("filename"):
                name = sanitize_filename(self.payload["filename"])
            self.name.setText(name)
            if not self._cat_touched:
                self._apply_category(categories.category_for(name))
        lines = []
        if info.get("kind") == "hls":
            seg = info.get("segments")
            dur = info.get("duration") or 0
            lines.append(f"<b>Luồng video HLS</b> — {seg or '?'} đoạn, ~{int(dur // 60)} phút {int(dur % 60)} giây")
            self.variant.clear()
            for v in info.get("variants", []):
                self.variant.addItem(v["label"], v["url"])
            has = self.variant.count() > 0
            self.variant.setVisible(has)
            self.variant_row.setVisible(has)
            if info.get("encrypted"):
                self.warn.setText("Luồng này được mã hoá/DRM — QT Downloader không tải nội dung được bảo vệ.")
                self.warn.show()
            elif info.get("live"):
                self.warn.setText("Đây là luồng trực tiếp (live) — chưa hỗ trợ.")
                self.warn.show()
        else:
            size = info.get("size", -1)
            lines.append(f"<b>Kích thước:</b> {fmt_size(size) if size >= 0 else 'không rõ'}")
            lines.append(f"<b>Loại:</b> {info.get('content_type') or '?'}")
            res = "Có ✔" if info.get("ranged") else "Không — nếu đứt sẽ phải tải lại từ đầu"
            lines.append(f"<b>Tạm dừng / tải tiếp:</b> {res}")
            if info.get("content_type", "").startswith("text/html"):
                self.warn.setText("Máy chủ trả về TRANG WEB chứ không phải tệp — có thể link cần đăng nhập hoặc đã "
                                  "hết hạn. Hãy tải từ trình duyệt (có extension) để mang theo cookie.")
                self.warn.show()
        final = info.get("final_url", "")
        if final and final != self.url.text().strip():
            lines.append(f"<b>Chuyển hướng tới:</b> {final[:90]}{'…' if len(final) > 90 else ''}")
        self.info_lbl.setText("<br>".join(lines))

    def submit(self, start_now: bool) -> None:
        url = self.url.text().strip()
        if not url:
            return
        name = sanitize_filename(self.name.text().strip(), "") or filename_from_url(url) or "download"
        kind = "hls" if (self.info or {}).get("kind") == "hls" or url.split("?")[0].lower().endswith(".m3u8") else "http"
        hls = {"variant": self.variant.currentData()} if kind == "hls" and self.variant.count() else None
        p = self.payload
        self.now_btn.setEnabled(False)
        self.later_btn.setEnabled(False)

        def done(ident, err):
            self.now_btn.setEnabled(True)
            self.later_btn.setEnabled(True)
            if err is not None:
                QMessageBox.warning(self, "Không thêm được", str(err))
                return
            self.added.emit(ident, start_now)
            self.accept()

        self.bridge.run(
            self.bridge.engine.add, url, filename=name, save_dir=self.dir.text().strip(),
            category=self.cat.currentData(), referer=self.referer.text().strip(), cookies=self.cookies.text().strip(),
            user_agent=p.get("userAgent", ""), page_url=p.get("pageUrl", ""),
            mirrors=[m for m in self.mirrors.toPlainText().splitlines() if m.strip()],
            connections=self.conns.value(), start=start_now, queue=not start_now,
            checksum=self.checksum.text().strip(), description=self.desc.text().strip(), kind=kind,
            size=(self.info or {}).get("size", -1) if kind == "http" else -1, hls=hls,
            speed_limit_kb=self.limit.value(), on_done=done,
        )


# ============================================================================ Tải hàng loạt
class BatchDialog(QDialog):
    def __init__(self, bridge: Bridge, payload: dict | None = None, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.payload = payload or {}
        self.setWindowTitle("Tải hàng loạt")
        self.setWindowIcon(icons.app_icon())
        self.resize(760, 540)
        lay = QVBoxLayout(self)
        if not self.payload.get("items"):
            lay.addWidget(_muted("Nhập mẫu có ký tự đại diện như IDM, ví dụ "
                                 "<code>https://site.vn/anh/[001-120].jpg</code> hoặc <code>…/[a-z].zip</code>; "
                                 "hoặc dán nhiều link, mỗi dòng một link."))
            self.pattern = QPlainTextEdit()
            self.pattern.setFixedHeight(80)
            lay.addWidget(self.pattern)
            self.pattern.textChanged.connect(self._from_pattern)
        else:
            src = self.payload.get("pageUrl", "")
            lay.addWidget(_muted(f"Các liên kết lấy từ trang: {src}"))
        frow = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Lọc theo đuôi tệp, vd: zip rar mp4 (để trống = tất cả)")
        frow.addWidget(self.filter, 1)
        all_b = QPushButton("Chọn hết")
        none_b = QPushButton("Bỏ chọn")
        frow.addWidget(all_b)
        frow.addWidget(none_b)
        lay.addLayout(frow)
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        self.count = _muted()
        lay.addWidget(self.count)
        form = QFormLayout()
        self.dir = QLineEdit(os.path.normpath(bridge.settings.download_dir))
        form.addRow("Lưu vào:", _dir_row(self.dir, self))
        self.use_cat = QCheckBox("Tự xếp vào thư mục con theo phân loại")
        self.use_cat.setChecked(bridge.settings.use_category_dirs)
        form.addRow("", self.use_cat)
        lay.addLayout(form)
        btns = QHBoxLayout()
        btns.addStretch(1)
        q = QPushButton(icons.icon("queue"), "Thêm vào hàng đợi")
        go = QPushButton(icons.icon("queue_start"), "Thêm và bắt đầu hàng đợi")
        go.setDefault(True)
        c = QPushButton("Huỷ")
        for b in (q, go, c):
            btns.addWidget(b)
        lay.addLayout(btns)
        all_b.clicked.connect(lambda: self._check_all(True))
        none_b.clicked.connect(lambda: self._check_all(False))
        self.filter.textChanged.connect(self._apply_filter)
        q.clicked.connect(lambda: self.submit(False))
        go.clicked.connect(lambda: self.submit(True))
        c.clicked.connect(self.reject)
        self.list.itemChanged.connect(lambda _: self._update_count())
        self._meta: dict[str, dict] = {}   # cookie/referer riêng từng link (cookie phải đúng host của link)
        for it in self.payload.get("items", []):
            self._meta[it.get("url", "")] = it
            self._add_row(it.get("url", ""), it.get("filename") or it.get("text", ""))
        self._apply_filter()

    def _add_row(self, url: str, label: str = "") -> None:
        name = filename_from_url(url) or url
        text = f"{name}    —    {url}" if not label or label == name else f"{name}  ({label[:60]})    —    {url}"
        item = QListWidgetItem(icons.file_icon(os.path.splitext(name)[1].lower()), text)
        item.setData(Qt.ItemDataRole.UserRole, url)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        self.list.addItem(item)

    def _from_pattern(self) -> None:
        self.list.clear()
        urls: list[str] = []
        for line in self.pattern.toPlainText().splitlines():
            line = line.strip()
            if line.lower().startswith(("http://", "https://")):
                urls += expand_batch_pattern(line, limit=5000 - len(urls))
        for u in urls[:5000]:
            self._add_row(u)
        self._apply_filter()

    def _apply_filter(self) -> None:
        exts = {e.strip().lower().lstrip(".") for e in self.filter.text().replace(",", " ").split() if e.strip()}
        for i in range(self.list.count()):
            it = self.list.item(i)
            url = it.data(Qt.ItemDataRole.UserRole)
            ext = os.path.splitext(filename_from_url(url))[1].lower().lstrip(".")
            it.setHidden(bool(exts) and ext not in exts)
        self._update_count()

    def _check_all(self, on: bool) -> None:
        for i in range(self.list.count()):
            it = self.list.item(i)
            if not it.isHidden():
                it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def selected_urls(self) -> list[str]:
        out = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if not it.isHidden() and it.checkState() == Qt.CheckState.Checked:
                out.append(it.data(Qt.ItemDataRole.UserRole))
        return out

    def _update_count(self) -> None:
        self.count.setText(f"Đã chọn {len(self.selected_urls())} / {self.list.count()} liên kết")

    def submit(self, start_queue: bool) -> None:
        urls = self.selected_urls()
        if not urls:
            return
        eng = self.bridge.engine
        p = self.payload
        base = self.dir.text().strip()
        use_cat = self.use_cat.isChecked()

        meta = self._meta

        async def add_all():
            for u in urls:
                m = meta.get(u, {})
                name = sanitize_filename(m.get("filename", ""), "") or filename_from_url(u) or "download"
                cat = categories.category_for(name)
                d = os.path.join(base, categories.subdir(cat)) if use_cat else base
                await eng.add(u, filename=name, save_dir=d,
                              referer=m.get("referer") or p.get("referer", "") or p.get("pageUrl", ""),
                              cookies=m.get("cookies", ""), user_agent=m.get("userAgent") or p.get("userAgent", ""),
                              page_url=p.get("pageUrl", ""), start=False, queue=True)
            if start_queue:
                await eng.start_queue()
            return len(urls)

        self.bridge.run(add_all, on_done=lambda n, e: QMessageBox.warning(self, "Lỗi", str(e)) if e else None)
        self.accept()


# ============================================================================ Cài đặt
class SettingsDialog(QDialog):
    def __init__(self, bridge: Bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        s = bridge.settings
        self.setWindowTitle("Tuỳ chọn")
        self.setWindowIcon(icons.icon("settings"))
        self.setMinimumWidth(600)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        g = QWidget()
        f = QFormLayout(g)
        self.dl_dir = QLineEdit(os.path.normpath(s.download_dir))
        f.addRow("Thư mục tải mặc định:", _dir_row(self.dl_dir, self))
        self.use_cat = QCheckBox("Xếp tệp vào thư mục con theo phân loại (Compressed, Video…)")
        self.use_cat.setChecked(s.use_category_dirs)
        f.addRow("", self.use_cat)
        self.show_prog = QCheckBox("Hiện cửa sổ tiến trình khi bắt đầu tải")
        self.show_prog.setChecked(s.show_progress_dialog)
        f.addRow("", self.show_prog)
        self.show_done = QCheckBox("Hiện hộp thoại khi tải xong")
        self.show_done.setChecked(s.show_complete_dialog)
        f.addRow("", self.show_done)
        self.clip = QCheckBox("Theo dõi clipboard: tự hỏi tải khi sao chép link tệp")
        self.clip.setChecked(s.monitor_clipboard)
        f.addRow("", self.clip)
        self.tray = QCheckBox("Đóng cửa sổ thì thu nhỏ xuống khay hệ thống")
        self.tray.setChecked(s.minimize_to_tray)
        f.addRow("", self.tray)
        self.resume_start = QCheckBox("Mở app thì tự tải tiếp các tệp đang tải dở")
        self.resume_start.setChecked(s.resume_on_start)
        f.addRow("", self.resume_start)
        self.check_updates = QCheckBox("Tự kiểm tra phiên bản mới trên GitHub mỗi khi mở app")
        self.check_updates.setChecked(s.check_updates)
        f.addRow("", self.check_updates)
        self.auto_download_updates = QCheckBox("Tự tải ngầm bản mới, cài khi khởi động lại hoặc thoát app")
        self.auto_download_updates.setToolTip("Chỉ áp dụng cho bản cài bằng bộ cài (QTDownloader-…-setup.exe). "
                                              "Bản giải nén từ gói zip chỉ được báo có bản mới.")
        self.auto_download_updates.setChecked(s.auto_download_updates)
        self.check_updates.toggled.connect(self.auto_download_updates.setEnabled)
        self.auto_download_updates.setEnabled(s.check_updates)
        f.addRow("", self.auto_download_updates)
        self.autostart = QCheckBox("Khởi động cùng Windows (thu nhỏ xuống khay)")
        self.autostart.setChecked(s.autostart)
        self.autostart.setEnabled(sys.platform == "win32")
        f.addRow("", self.autostart)
        tabs.addTab(g, "Chung")

        c = QWidget()
        f = QFormLayout(c)
        self.max_conn = QSpinBox()
        self.max_conn.setRange(1, 32)
        self.max_conn.setValue(s.max_connections)
        f.addRow("Số kết nối tối đa / tệp:", self.max_conn)
        self.max_conc = QSpinBox()
        self.max_conc.setRange(1, 20)
        self.max_conc.setValue(s.max_concurrent)
        f.addRow("Số tệp tải cùng lúc (hàng đợi):", self.max_conc)
        self.glimit = QSpinBox()
        self.glimit.setRange(0, 10_000_000)
        self.glimit.setSuffix(" KB/s")
        self.glimit.setSpecialValueText("Không giới hạn")
        self.glimit.setValue(s.global_speed_limit_kb)
        f.addRow("Giới hạn tốc độ chung:", self.glimit)
        self.min_split = QSpinBox()
        self.min_split.setRange(256, 65536)
        self.min_split.setSuffix(" KB")
        self.min_split.setValue(s.min_split_kb)
        f.addRow("Kích thước đoạn tối thiểu:", self.min_split)
        self.retries = QSpinBox()
        self.retries.setRange(0, 100)
        self.retries.setValue(s.max_retries)
        f.addRow("Số lần thử lại:", self.retries)
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 300)
        self.timeout.setSuffix(" giây")
        self.timeout.setValue(s.timeout)
        f.addRow("Thời gian chờ:", self.timeout)
        self.http2 = QCheckBox("Dùng HTTP/2 (mọi kết nối gộp vào 1 kết nối TCP — thường CHẬM hơn khi tải đa luồng)")
        self.http2.setChecked(s.http2)
        f.addRow("", self.http2)
        self.proxy = QLineEdit(s.proxy)
        self.proxy.setPlaceholderText("trống = theo hệ thống · vd http://127.0.0.1:8080")
        f.addRow("Proxy:", self.proxy)
        self.ua = QLineEdit(s.user_agent)
        f.addRow("User-Agent:", self.ua)
        self.verify = QCheckBox("Kiểm tra chứng chỉ TLS (khuyến nghị bật)")
        self.verify.setChecked(s.verify_tls)
        f.addRow("", self.verify)
        tabs.addTab(c, "Kết nối")

        b = QWidget()
        f = QFormLayout(b)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(s.api_port)
        f.addRow("Cổng nhận link từ trình duyệt:", self.port)
        self.ask = QCheckBox("Hiện hộp thoại xác nhận khi trình duyệt chuyển link sang")
        self.ask.setChecked(s.browser_ask)
        f.addRow("", self.ask)
        self.protocol = QCheckBox("Cho phép trình duyệt mở QT Downloader (giao thức qtdownloader://)")
        self.protocol.setChecked(s.browser_protocol)
        self.protocol.setEnabled(sys.platform == "win32")
        pbox = QVBoxLayout()
        pbox.setSpacing(2)
        pbox.addWidget(self.protocol)
        phint = _muted("Khi app chưa chạy, bấm “Tải bằng QT Downloader” hoặc nút “Mở QT Downloader” trên extension sẽ "
                       "mở app (trình duyệt hỏi có mở QT Downloader không — chọn Mở, tích “luôn cho phép” để lần sau "
                       "khỏi hỏi). Ghi vào "
                       "<code>HKCU\\Software\\Classes\\qtdownloader</code>; bỏ chọn thì gỡ.")
        phint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        pbox.addWidget(phint)
        f.addRow("", pbox)
        self.exts = QPlainTextEdit(s.capture_exts)
        self.exts.setFixedHeight(90)
        f.addRow("Đuôi tệp tự bắt:", self.exts)
        state = "đang chạy ✔" if not bridge.engine.api_error else bridge.engine.api_error
        f.addRow("Trạng thái:", QLabel(state))
        ext_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "extension"))
        guide = _muted("Cài extension: mở <b>chrome://extensions</b> (hoặc edge://extensions) → bật <i>Chế độ dành "
                       "cho nhà phát triển</i> → <i>Tải tiện ích đã giải nén</i> → chọn thư mục:<br>"
                       f"<code>{ext_dir}</code>")
        guide.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        f.addRow(guide)
        ob = QPushButton(icons.icon("folder"), "Mở thư mục extension")
        ob.clicked.connect(lambda: open_path(ext_dir))
        f.addRow("", ob)
        tabs.addTab(b, "Trình duyệt")

        m = QWidget()
        f = QFormLayout(m)
        self.ffmpeg = QLineEdit(s.ffmpeg_path)
        self.ffmpeg.setPlaceholderText("trống = tìm ffmpeg trong PATH (để chuyển .ts → .mp4)")
        f.addRow("ffmpeg.exe:", self.ffmpeg)
        self.sidecar = QCheckBox("Tự tìm tệp .sha256 cạnh link để kiểm tra toàn vẹn sau khi tải")
        self.sidecar.setChecked(s.auto_checksum_sidecar)
        f.addRow("", self.sidecar)
        tabs.addTab(m, "Video && kiểm tra")

        bb = vi_buttons(QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel))
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _apply_integration(self) -> tuple[bool, bool]:
        """Ghi/gỡ registry theo ô đã chọn; lỗi thì giữ nguyên trạng thái cũ."""
        s = self.bridge.settings
        proto, auto = self.protocol.isChecked(), self.autostart.isChecked()
        if proto != s.browser_protocol:
            try:
                integration.register_protocol() if proto else integration.unregister_protocol()
            except OSError as e:
                proto = s.browser_protocol
                QMessageBox.warning(self, "Lỗi", f"Không ghi được registry cho giao thức qtdownloader://:\n{e}")
        if auto != s.autostart:
            try:
                integration.set_autostart(auto)
            except OSError as e:
                auto = s.autostart
                QMessageBox.warning(self, "Lỗi", f"Không đặt được khởi động cùng Windows:\n{e}")
        return proto, auto

    def save(self) -> None:
        port_changed = self.port.value() != self.bridge.settings.api_port
        proto, auto = self._apply_integration()
        values = dict(
            download_dir=self.dl_dir.text().strip() or self.bridge.settings.download_dir,
            use_category_dirs=self.use_cat.isChecked(), show_progress_dialog=self.show_prog.isChecked(),
            show_complete_dialog=self.show_done.isChecked(), monitor_clipboard=self.clip.isChecked(),
            minimize_to_tray=self.tray.isChecked(), resume_on_start=self.resume_start.isChecked(),
            check_updates=self.check_updates.isChecked(),
            auto_download_updates=self.auto_download_updates.isChecked(),
            max_connections=self.max_conn.value(), max_concurrent=self.max_conc.value(),
            global_speed_limit_kb=self.glimit.value(), min_split_kb=self.min_split.value(),
            max_retries=self.retries.value(), timeout=self.timeout.value(), http2=self.http2.isChecked(),
            proxy=self.proxy.text().strip(), user_agent=self.ua.text().strip(), verify_tls=self.verify.isChecked(),
            api_port=self.port.value(), browser_ask=self.ask.isChecked(),
            capture_exts=" ".join(self.exts.toPlainText().split()), ffmpeg_path=self.ffmpeg.text().strip(),
            auto_checksum_sidecar=self.sidecar.isChecked(), browser_protocol=proto, autostart=auto,
        )
        self.bridge.run(self.bridge.engine.update_settings, values)
        if port_changed:
            QMessageBox.information(self, "Cần khởi động lại", "Cổng mới có hiệu lực sau khi mở lại QT Downloader. "
                                    "Nhớ đổi cổng tương ứng trong tuỳ chọn của extension.")
        self.accept()


# ============================================================================ Lịch hẹn
class SchedulerDialog(QDialog):
    DAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
    ACTIONS = [("none", "Không làm gì"), ("exit", "Thoát QT Downloader"), ("sleep", "Cho máy ngủ (Sleep)"),
               ("shutdown", "Tắt máy")]

    def __init__(self, bridge: Bridge, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QTime
        self.bridge = bridge
        sch = bridge.settings.schedule
        self.setWindowTitle("Lịch hẹn hàng đợi")
        self.setWindowIcon(icons.icon("schedule"))
        lay = QVBoxLayout(self)
        self.enabled = QCheckBox("Bật lịch hẹn")
        self.enabled.setChecked(sch.enabled)
        lay.addWidget(self.enabled)
        grid = QGridLayout()
        grid.addWidget(QLabel("Bắt đầu hàng đợi lúc:"), 0, 0)
        self.start = QTimeEdit(QTime.fromString(sch.start_time, "HH:mm"))
        self.start.setDisplayFormat("HH:mm")
        grid.addWidget(self.start, 0, 1)
        self.stop_on = QCheckBox("Dừng hàng đợi lúc:")
        self.stop_on.setChecked(bool(sch.stop_time))
        grid.addWidget(self.stop_on, 1, 0)
        self.stop = QTimeEdit(QTime.fromString(sch.stop_time or "07:00", "HH:mm"))
        self.stop.setDisplayFormat("HH:mm")
        grid.addWidget(self.stop, 1, 1)
        lay.addLayout(grid)
        days = QHBoxLayout()
        days.addWidget(QLabel("Các ngày:"))
        self.day_boxes = []
        for i, d in enumerate(self.DAYS):
            cb = QCheckBox(d)
            cb.setChecked(i in sch.days)
            self.day_boxes.append(cb)
            days.addWidget(cb)
        lay.addLayout(days)
        row = QHBoxLayout()
        row.addWidget(QLabel("Khi hàng đợi xong:"))
        self.after = QComboBox()
        for key, label in self.ACTIONS:
            self.after.addItem(label, key)
        self.after.setCurrentIndex(max(0, self.after.findData(sch.after_done)))
        row.addWidget(self.after, 1)
        lay.addLayout(row)
        lay.addWidget(_muted("Mẹo: hẹn giờ ban đêm để tận dụng gói cước/giờ thấp điểm. Các tệp 'Tải sau' "
                             "nằm trong nhóm Hàng đợi."))
        bb = vi_buttons(QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel))
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def save(self) -> None:
        sch = {
            "enabled": self.enabled.isChecked(), "start_time": self.start.time().toString("HH:mm"),
            "stop_time": self.stop.time().toString("HH:mm") if self.stop_on.isChecked() else "",
            "days": [i for i, cb in enumerate(self.day_boxes) if cb.isChecked()],
            "after_done": self.after.currentData(),
        }
        self.bridge.run(self.bridge.engine.update_settings, {"schedule": sch})
        self.accept()


# ============================================================================ Thuộc tính
class PropertiesDialog(QDialog):
    def __init__(self, bridge: Bridge, ident: str, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.ident = ident
        it = bridge.item(ident) or {}
        self.setWindowTitle(f"Thuộc tính — {it.get('filename', '')}")
        self.setWindowIcon(icons.icon("info"))
        self.setMinimumWidth(640)
        lay = QVBoxLayout(self)
        form = QFormLayout()

        def ro(text):
            e = QLineEdit(str(text))
            e.setReadOnly(True)
            e.setCursorPosition(0)
            return e

        form.addRow("Tệp:", ro(it.get("path", "")))
        form.addRow("Kích thước:", QLabel(fmt_size(it.get("size", -1))))
        form.addRow("Trạng thái:", QLabel(it.get("status_text", "")))
        if it.get("error"):
            lb = QLabel(it["error"])
            lb.setWordWrap(True)
            lb.setStyleSheet("color:#dc2626")
            form.addRow("Lỗi:", lb)
        form.addRow("Tiếp tục được:", QLabel({True: "Có", False: "Không"}.get(it.get("resumable"), "Chưa rõ")))
        self.url = QLineEdit(it.get("url", ""))
        form.addRow("Địa chỉ:", self.url)
        if it.get("referer"):
            form.addRow("Referer:", ro(it["referer"]))
        if it.get("mirrors"):
            form.addRow("Nguồn phụ:", ro(" | ".join(it["mirrors"])))
        if it.get("checksum"):
            ok = {True: " ✔ khớp", False: " ✘ KHÔNG khớp"}.get(it.get("checksum_ok"), "")
            form.addRow("Checksum:", ro(it["checksum"] + ok))
        self.desc = QLineEdit(it.get("description", ""))
        form.addRow("Mô tả:", self.desc)
        lay.addLayout(form)
        lay.addWidget(_muted("Link hết hạn? Dán link mới vào ô Địa chỉ rồi bấm 'Cập nhật địa chỉ tải' — QT Downloader "
                             "kiểm tra cùng kích thước rồi tải tiếp phần còn lại (giống Refresh download address của IDM)."))
        bb = QHBoxLayout()
        refresh = QPushButton(icons.icon("link"), "Cập nhật địa chỉ tải")
        bb.addWidget(refresh)
        bb.addStretch(1)
        ok = QPushButton("Lưu")
        ok.setDefault(True)
        cancel = QPushButton("Đóng")
        bb.addWidget(ok)
        bb.addWidget(cancel)
        lay.addLayout(bb)
        self._orig_url = it.get("url", "")
        refresh.clicked.connect(self.refresh)
        ok.clicked.connect(self.save)
        cancel.clicked.connect(self.reject)

    def refresh(self) -> None:
        new = self.url.text().strip()
        if not new or new == self._orig_url:
            QMessageBox.information(self, "Cập nhật địa chỉ", "Hãy dán link mới (khác link cũ) vào ô Địa chỉ.")
            return

        def done(msg, err):
            if err or msg:
                QMessageBox.warning(self, "Không cập nhật được", str(err or msg))
            else:
                QMessageBox.information(self, "Đã cập nhật", "Đã nhận link mới, đang tải tiếp.")
                self.accept()

        self.bridge.run(self.bridge.engine.refresh_url, self.ident, new, on_done=done)

    def save(self) -> None:
        self.bridge.run(self.bridge.engine.update_item, self.ident, description=self.desc.text().strip())
        self.accept()


# ============================================================================ Tải xong
class CompleteDialog(QDialog):
    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle("Tải xong")
        self.setWindowIcon(icons.app_icon())
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.file_icon(os.path.splitext(item["filename"])[1].lower()).pixmap(48, 48))
        head.addWidget(ic)
        title = QLabel(item["filename"])
        f = QFont(title.font())
        f.setPointSizeF(f.pointSizeF() + 2)
        f.setBold(True)
        title.setFont(f)
        title.setWordWrap(True)
        head.addWidget(title, 1)
        lay.addLayout(head)
        path = QLineEdit(item["path"])
        path.setReadOnly(True)
        lay.addWidget(path)
        info = f"Kích thước: {fmt_size(item.get('size', -1))}"
        if item.get("checksum_ok") is True:
            info += "   ·   Checksum: <span style='color:#16a34a'>✔ khớp</span>"
        elif item.get("checksum_ok") is False:
            info += "   ·   Checksum: <span style='color:#dc2626'>✘ KHÔNG khớp — tệp có thể bị hỏng</span>"
        lay.addWidget(QLabel(info))
        btns = QHBoxLayout()
        self.again = QCheckBox("Không hiện hộp thoại này nữa")
        btns.addWidget(self.again)
        btns.addStretch(1)
        o = QPushButton(icons.icon("open"), "Mở")
        o.setDefault(True)
        d = QPushButton(icons.icon("folder"), "Mở thư mục")
        c = QPushButton("Đóng")
        for b in (o, d, c):
            btns.addWidget(b)
        lay.addLayout(btns)
        o.clicked.connect(lambda: (open_path(item["path"]), self.accept()))
        d.clicked.connect(lambda: (reveal_path(item["path"]), self.accept()))
        c.clicked.connect(self.accept)


# ============================================================================ Đếm ngược
class UpdateDialog(QDialog):
    """Báo có phiên bản mới trên GitHub Releases."""

    downloaded = Signal(str)   # id mục tải gói cập nhật (bản giải nén: gói zip hiện trong danh sách tải)
    preparing = Signal()       # bản đã cài: bắt đầu tải ngầm bộ cài

    def __init__(self, bridge: Bridge, info: dict, parent=None):
        super().__init__(parent)
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        from PySide6.QtWidgets import QTextBrowser
        from .. import __version__
        self.bridge = bridge
        self.info = info
        self.setWindowTitle("Có phiên bản mới")
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(560, 420)
        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_pixmap(48))
        head.addWidget(logo)
        title = QLabel(f"<b style='font-size:15px'>QT Downloader {info['version']} đã phát hành</b><br>"
                       f"<span style='color:gray'>Bạn đang dùng {__version__}"
                       f"{' · ' + info['published'][:10] if info.get('published') else ''}</span>")
        head.addWidget(title, 1)
        lay.addLayout(head)
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(info.get("notes") or "_(Bản phát hành không có ghi chú)_")
        lay.addWidget(notes, 1)
        installed = bool(getattr(bridge.engine, "installed", False))
        if info.get("setup_url") and (installed or not info.get("asset_url")):
            size = fmt_size(info.get("setup_size") or -1)
            chk = " · có kiểm SHA-256" if info.get("setup_sha256") else ""
            lay.addWidget(_muted(f"Bộ cài: {info['setup_name']} ({size}){chk}. Tải ngầm xong, bấm “Khởi động lại để cập "
                                 "nhật” ở thanh trạng thái — hoặc bản mới tự cài khi bạn thoát app (dữ liệu và danh "
                                 "sách tải được giữ nguyên)."))
        elif info.get("asset_url"):
            size = fmt_size(info.get("asset_size") or -1)
            chk = " · có kiểm SHA-256" if info.get("sha256") else ""
            lay.addWidget(_muted(f"Gói tải: {info['asset_name']} ({size}){chk}. Tải xong, đóng QT Downloader rồi giải nén "
                                 "đè lên thư mục cũ (dữ liệu và danh sách tải được giữ nguyên)."))
        btns = QHBoxLayout()
        skip = QPushButton("Bỏ qua bản này")
        later = QPushButton("Để sau")
        page = QPushButton(icons.icon("globe"), "Xem trên GitHub")
        get = QPushButton(icons.icon("all"), "Tải bản mới")
        get.setDefault(True)
        get.setVisible(bool(info.get("asset_url") or info.get("setup_url")))
        page.setVisible(bool(info.get("page_url")))
        btns.addWidget(skip)
        btns.addStretch(1)
        for b in (page, later, get):
            btns.addWidget(b)
        lay.addLayout(btns)
        page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(info["page_url"])))
        later.clicked.connect(self.reject)
        skip.clicked.connect(self._skip)
        get.clicked.connect(self._download)

    def _skip(self) -> None:
        self.bridge.run(self.bridge.engine.skip_update, self.info["version"])
        self.reject()

    def _download(self) -> None:
        info = self.info
        if info.get("setup_url") and info.get("setup_sha256") and getattr(self.bridge.engine, "installed", False):
            def started(ok, err):
                if err is not None or not ok:
                    QMessageBox.warning(self, "Không tải được bản mới", str(err or "Bản phát hành không có bộ cài"))
                    return
                self.preparing.emit()
                self.accept()
            self.bridge.run(self.bridge.engine.prepare_update, on_done=started)
            return

        def done(ident, err):
            if err is not None:
                QMessageBox.warning(self, "Không tải được bản mới", str(err))
                return
            self.downloaded.emit(ident)
            self.accept()
        self.bridge.run(self.bridge.engine.download_update, on_done=done)


class CountdownDialog(QDialog):
    def __init__(self, action_label: str, seconds: int = 60, parent=None):
        super().__init__(parent)
        self.remaining = seconds
        self.action_label = action_label
        self.setWindowTitle("Hàng đợi đã xong")
        self.setWindowIcon(icons.app_icon())
        lay = QVBoxLayout(self)
        self.lbl = QLabel()
        lay.addWidget(self.lbl)
        bb = QHBoxLayout()
        now = QPushButton("Làm ngay")
        cancel = QPushButton("Huỷ")
        cancel.setDefault(True)
        bb.addStretch(1)
        bb.addWidget(now)
        bb.addWidget(cancel)
        lay.addLayout(bb)
        now.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._tick(first=True)

    def _tick(self, first: bool = False) -> None:
        if not first:
            self.remaining -= 1
        if self.remaining <= 0:
            self.timer.stop()
            self.accept()
            return
        self.lbl.setText(f"Mọi tệp trong hàng đợi đã tải xong.\n{self.action_label} sau {self.remaining} giây…")


def settings_snapshot(settings) -> dict:
    return asdict(settings)

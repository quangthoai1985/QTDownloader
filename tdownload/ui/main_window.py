"""Cửa sổ chính của TDownload."""

from __future__ import annotations

import os
import re
import subprocess
import sys

from PySide6.QtCore import QItemSelectionModel, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QSplitter, QSystemTrayIcon, QTableView, QTabWidget, QToolBar,
    QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import __version__
from ..core import categories
from ..core.util import filename_from_url, fmt_speed
from . import icons
from .bridge import Bridge, open_path, reveal_path
from .dialogs import (AddUrlDialog, BatchDialog, CompleteDialog, CountdownDialog, PropertiesDialog,
                      SchedulerDialog, SettingsDialog, ask)
from .progress_dialog import ProgressDialog
from .table_model import ID_ROLE, DownloadFilter, DownloadTableModel
from .widgets import ProgressDelegate

URL_RE = re.compile(r"^https?://\S+$", re.I)


def parse_ef2(text: str) -> list[dict]:
    """Đọc tệp xuất danh sách của IDM (.ef2) để chuyển sang TDownload."""
    items, cur = [], None
    for line in text.replace("\r", "").split("\n"):
        line = line.strip()
        if line == "<":
            cur = {}
        elif line == ">":
            if cur and cur.get("url"):
                items.append(cur)
            cur = None
        elif cur is not None:
            if "url" not in cur and URL_RE.match(line):
                cur["url"] = line
            elif ":" in line:
                k, v = line.split(":", 1)
                k = k.strip().lower()
                if k in ("referer", "cookie", "user-agent", "filename"):
                    cur[{"cookie": "cookies", "user-agent": "userAgent"}.get(k, k)] = v.strip()
    return items


class MainWindow(QMainWindow):
    def __init__(self, bridge: Bridge):
        super().__init__()
        self.bridge = bridge
        self.engine = bridge.engine
        self.progress_dialogs: dict[str, ProgressDialog] = {}
        self._open_dialogs: list = []
        self._ver = -1
        self._last_clip = ""
        self._tray_hint_shown = False
        self.quitting = False
        self.setWindowTitle("TDownload — Trình tăng tốc tải xuống")
        self.setWindowIcon(icons.app_icon())
        self.resize(1180, 680)
        self.setAcceptDrops(True)

        self._build_actions()
        self._build_toolbar()
        self._build_menu()
        self._build_central()
        self._build_statusbar()
        self._build_tray()

        self.bridge.event.connect(self.on_event)
        QApplication.clipboard().dataChanged.connect(self.on_clipboard)
        self._last_clip = QApplication.clipboard().text().strip()
        self.timer = QTimer(self, interval=400)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()
        if self.engine.api_error:
            self.statusBar().showMessage(self.engine.api_error, 15000)

    # ------------------------------------------------------------------ dựng giao diện
    def _act(self, icon, text, slot, shortcut=None, tip=None) -> QAction:
        a = QAction(icons.icon(icon) if icon else QIcon(), text, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip)
        return a

    def _build_actions(self) -> None:
        self.a_add = self._act("add", "Thêm URL", lambda: self.show_add_dialog(), "Ctrl+N", "Thêm link tải (Ctrl+N)")
        self.a_resume = self._act("resume", "Tiếp tục", self.resume_selected, "Ctrl+R")
        self.a_pause = self._act("pause", "Dừng", self.pause_selected, "Ctrl+P")
        self.a_stop_all = self._act("stop_all", "Dừng tất cả", lambda: self.bridge.run(self.engine.pause_all))
        self.a_resume_all = self._act("resume", "Tiếp tục tất cả", lambda: self.bridge.run(self.engine.resume_all))
        self.a_delete = self._act("delete", "Xoá", self.delete_selected, QKeySequence.StandardKey.Delete)
        self.a_clean = self._act("clean", "Xoá đã xong", self.delete_completed,
                                 tip="Xoá khỏi danh sách các tệp đã tải xong (không xoá tệp trên đĩa)")
        self.a_settings = self._act("settings", "Tuỳ chọn", self.show_settings)
        self.a_schedule = self._act("schedule", "Lịch hẹn", self.show_scheduler)
        self.a_qstart = self._act("queue_start", "Chạy hàng đợi", lambda: self.bridge.run(self.engine.start_queue))
        self.a_qstop = self._act("queue_stop", "Dừng hàng đợi", lambda: self.bridge.run(self.engine.stop_queue))
        self.a_batch = self._act("batch", "Tải hàng loạt", lambda: self.show_batch(), "Ctrl+B")
        self.a_open = self._act("open", "Mở tệp", self.open_selected)
        self.a_reveal = self._act("folder", "Mở thư mục", self.reveal_selected)
        self.a_restart = self._act("restart", "Tải lại từ đầu", self.restart_selected)
        self.a_props = self._act("info", "Thuộc tính / cập nhật link…", self.props_selected, "Alt+Return")
        self.a_copy = self._act("link", "Chép địa chỉ", self.copy_url)
        self.a_queue_add = self._act("queue", "Đưa vào hàng đợi", lambda: self._queue_selected(True))
        self.a_queue_rm = self._act(None, "Bỏ khỏi hàng đợi", lambda: self._queue_selected(False))
        self.a_up = self._act(None, "Lên đầu hàng đợi một bậc", lambda: self._move_selected(-1))
        self.a_down = self._act(None, "Xuống một bậc", lambda: self._move_selected(1))
        self.a_limit = self._act("speed", "Giới hạn tốc độ tệp này…", self.limit_selected)
        self.a_import = self._act(None, "Nhập danh sách (.txt / .ef2 của IDM)…", self.import_list)
        self.a_export = self._act(None, "Xuất danh sách link…", self.export_list)
        self.a_quit = self._act(None, "Thoát", self.quit_app, "Ctrl+Q")
        self.a_about = self._act("info", "Giới thiệu", self.show_about)
        self.a_paste = QAction(self)
        self.a_paste.setShortcut(QKeySequence.StandardKey.Paste)
        self.a_paste.triggered.connect(self.paste_url)
        self.addAction(self.a_paste)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Thanh công cụ")
        tb.setMovable(False)
        tb.setIconSize(QSize(28, 28))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        for a in (self.a_add, self.a_resume, self.a_pause, self.a_stop_all, self.a_delete, self.a_clean, None,
                  self.a_settings, self.a_schedule, self.a_qstart, self.a_qstop, None, self.a_batch):
            if a is None:
                tb.addSeparator()
            else:
                tb.addAction(a)
        self.addToolBar(tb)

    def _build_menu(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("&Tệp")
        for a in (self.a_add, self.a_batch, None, self.a_import, self.a_export, None, self.a_quit):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu("Tải &xuống")
        for a in (self.a_resume, self.a_pause, None, self.a_resume_all, self.a_stop_all, None, self.a_qstart,
                  self.a_qstop, self.a_schedule, None, self.a_delete, self.a_clean):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu("&Công cụ")
        m.addAction(self.a_settings)
        m.addAction(self._act("speed", "Giới hạn tốc độ chung…", self.limit_global))
        m = mb.addMenu("Trợ &giúp")
        m.addAction(self._act("globe", "Cài extension trình duyệt…", lambda: self.show_settings(tab=2)))
        m.addAction(self.a_about)

    def _build_central(self) -> None:
        split = QSplitter()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.setMinimumWidth(170)
        self.tree_items: dict[str, QTreeWidgetItem] = {}

        def node(key, label, icon, parent=None):
            it = QTreeWidgetItem([label])
            it.setIcon(0, icons.icon(icon))
            it.setData(0, Qt.ItemDataRole.UserRole, key)
            it.setData(0, Qt.ItemDataRole.UserRole + 1, label)
            (parent.addChild(it) if parent else self.tree.addTopLevelItem(it))
            self.tree_items[key] = it
            return it

        root = node("all", "Tất cả", "all")
        for key in categories.ORDER:
            node("cat:" + key, categories.display_name(key), key, root)
        node("unfinished", "Chưa xong", "unfinished")
        node("finished", "Đã xong", "finished")
        node("queue", "Hàng đợi", "queue")
        self.tree.expandAll()
        self.tree.setCurrentItem(root)
        self.tree.currentItemChanged.connect(self._on_group)
        split.addWidget(self.tree)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm theo tên tệp hoặc link…")
        self.search.setClearButtonEnabled(True)
        top.addWidget(self.search)
        rl.addLayout(top)
        self.model = DownloadTableModel(self)
        self.proxy = DownloadFilter(self)
        self.proxy.setSourceModel(self.model)
        self.search.textChanged.connect(self.proxy.set_text)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(5, Qt.SortOrder.DescendingOrder)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setShowGrid(False)
        self.view.setAlternatingRowColors(True)
        self.view.verticalHeader().hide()
        self.view.verticalHeader().setDefaultSectionSize(30)
        self.view.setWordWrap(False)
        self.view.setIconSize(QSize(18, 18))
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._context_menu)
        self.view.doubleClicked.connect(self._on_double_click)
        self.view.setItemDelegateForColumn(2, ProgressDelegate(self.view))
        h = self.view.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, w in ((1, 95), (2, 150), (3, 110), (4, 100), (5, 125), (6, 200)):
            self.view.setColumnWidth(col, w)
        h.setStretchLastSection(False)
        self.view.selectionModel().selectionChanged.connect(lambda *_: self._update_actions())
        rl.addWidget(self.view)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([200, 980])
        self.setCentralWidget(split)

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.lbl_speed = QLabel()
        self.lbl_active = QLabel()
        self.lbl_queue = QLabel()
        self.lbl_api = QLabel()
        self.limit_btn = QToolButton()
        self.limit_btn.setIcon(icons.icon("speed"))
        self.limit_btn.setAutoRaise(True)
        self.limit_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.limit_btn)
        for kb in (0, 128, 256, 512, 1024, 2048, 5120, 10240):
            label = "Không giới hạn" if kb == 0 else (f"{kb} KB/s" if kb < 1024 else f"{kb // 1024} MB/s")
            menu.addAction(label, lambda kb=kb: self._set_global_limit(kb))
        menu.addSeparator()
        menu.addAction("Tuỳ chỉnh…", self.limit_global)
        self.limit_btn.setMenu(menu)
        for w in (self.lbl_speed, self.lbl_active, self.lbl_queue, self.lbl_api, self.limit_btn):
            sb.addPermanentWidget(w)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(icons.app_icon(), self)
        m = QMenu()
        m.addAction(icons.app_icon(), "Mở TDownload", self.show_window)
        m.addAction(self.a_add)
        m.addAction(self.a_batch)
        m.addSeparator()
        m.addAction(self.a_resume_all)
        m.addAction(self.a_stop_all)
        m.addSeparator()
        m.addAction(self.a_quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: self.show_window() if r in (
            QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        self.tray.messageClicked.connect(self.show_window)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    # ------------------------------------------------------------------ cập nhật định kỳ
    def refresh(self) -> None:
        snap = self.engine.snapshot
        if snap["version"] == self._ver:
            return
        self._ver = snap["version"]
        items = snap["items"]
        selected = self.selected_ids()
        if self.model.update_from(items):
            self._restore_selection(selected)
        counts = {"all": len(items), "unfinished": 0, "finished": 0, "queue": 0}
        for it in items.values():
            counts["cat:" + it["category"]] = counts.get("cat:" + it["category"], 0) + 1
            counts["finished" if it["status"] == "completed" else "unfinished"] += 1
            if it["status"] == "queued":
                counts["queue"] += 1
        for key, node in self.tree_items.items():
            label = node.data(0, Qt.ItemDataRole.UserRole + 1)
            n = counts.get(key, 0)
            node.setText(0, f"{label} ({n})" if n else label)
        speed = snap["speed"]
        active = snap["active"]
        self.lbl_speed.setText(f"↓ {fmt_speed(speed) or '0 B/s'}")
        self.lbl_active.setText(f"Đang tải: {active}")
        self.lbl_queue.setText("Hàng đợi: đang chạy" if snap["queue_running"] else "Hàng đợi: dừng")
        if snap.get("api_error"):
            self.lbl_api.setText("Trình duyệt: ✘")
            self.lbl_api.setToolTip(snap["api_error"])
        else:
            self.lbl_api.setText(f"Trình duyệt: ✔ cổng {self.bridge.settings.api_port}")
            self.lbl_api.setToolTip("Extension gửi link tới 127.0.0.1:" + str(self.bridge.settings.api_port))
        lim = self.bridge.settings.global_speed_limit_kb
        self.limit_btn.setText(f" {lim} KB/s" if lim else "")
        self.limit_btn.setToolTip("Giới hạn tốc độ chung: " + (f"{lim} KB/s" if lim else "không"))
        self.limit_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if lim
                                          else Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.tray.setToolTip(f"TDownload — {active} đang tải · {fmt_speed(speed) or '0 B/s'}")
        self.tray.setIcon(icons.tray_icon(active > 0))
        title = "TDownload — Trình tăng tốc tải xuống"
        if active:
            title = f"↓ {fmt_speed(speed)} · {active} tệp — TDownload"
        self.setWindowTitle(title)
        for pd in list(self.progress_dialogs.values()):
            if pd.isVisible():
                pd.refresh()
        self._update_actions()

    def _update_actions(self) -> None:
        sel = [self.bridge.item(i) for i in self.selected_ids()]
        sel = [s for s in sel if s]
        has = bool(sel)
        self.a_resume.setEnabled(any(not s["active"] and s["status"] != "completed" for s in sel))
        self.a_pause.setEnabled(any(s["active"] for s in sel))
        self.a_delete.setEnabled(has)
        one = len(sel) == 1
        for a in (self.a_open,):
            a.setEnabled(one and sel[0]["status"] == "completed")
        self.a_reveal.setEnabled(one)
        self.a_props.setEnabled(one)
        self.a_copy.setEnabled(has)
        self.a_restart.setEnabled(has)
        self.a_limit.setEnabled(one)
        q_running = self.engine.snapshot.get("queue_running")
        self.a_qstart.setEnabled(not q_running)
        self.a_qstop.setEnabled(bool(q_running))

    # ------------------------------------------------------------------ chọn dòng
    def selected_ids(self) -> list[str]:
        sm = self.view.selectionModel()
        return [self.proxy.index(ix.row(), 0).data(ID_ROLE) for ix in sm.selectedRows()] if sm else []

    def _restore_selection(self, ids: list[str]) -> None:
        if not ids:
            return
        sm = self.view.selectionModel()
        want = set(ids)
        for row in range(self.proxy.rowCount()):
            ix = self.proxy.index(row, 0)
            if ix.data(ID_ROLE) in want:
                sm.select(ix, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)

    def _on_group(self, cur, _prev) -> None:
        if cur is not None:
            self.proxy.set_group(cur.data(0, Qt.ItemDataRole.UserRole))

    # ------------------------------------------------------------------ hành động
    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _keep(self, dlg) -> None:
        self._open_dialogs.append(dlg)
        dlg.finished.connect(lambda *_: self._open_dialogs.remove(dlg) if dlg in self._open_dialogs else None)

    def show_add_dialog(self, url: str = "", payload: dict | None = None) -> None:
        if not url and not payload:
            clip = QApplication.clipboard().text().strip()
            if URL_RE.match(clip):
                url = clip
        dlg = AddUrlDialog(self.bridge, url, payload, None if payload else self)
        if payload:  # đến từ trình duyệt → nổi lên trên cùng như IDM
            dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dlg.added.connect(self._on_added)
        self._keep(dlg)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_added(self, ident: str, started: bool) -> None:
        if started and self.bridge.settings.show_progress_dialog:
            QTimer.singleShot(500, lambda: self.show_progress(ident))

    def show_batch(self, payload: dict | None = None) -> None:
        dlg = BatchDialog(self.bridge, payload, None if payload else self)
        if payload:
            dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._keep(dlg)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def show_progress(self, ident: str) -> None:
        if self.bridge.item(ident) is None:
            return
        pd = self.progress_dialogs.get(ident)
        if pd is None:
            pd = ProgressDialog(self.bridge, ident, None)
            self.progress_dialogs[ident] = pd
            pd.destroyed.connect(lambda *_: self.progress_dialogs.pop(ident, None))
            pd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        pd.refresh()
        pd.show()
        pd.raise_()
        pd.activateWindow()

    def show_settings(self, tab: int = 0) -> None:
        dlg = SettingsDialog(self.bridge, self)
        tw = dlg.findChild(QTabWidget)
        if tw is not None:
            tw.setCurrentIndex(tab)
        dlg.exec()

    def show_scheduler(self) -> None:
        SchedulerDialog(self.bridge, self).exec()

    def resume_selected(self) -> None:
        for i in self.selected_ids():
            self.bridge.run(self.engine.resume, i)

    def pause_selected(self) -> None:
        for i in self.selected_ids():
            self.bridge.run(self.engine.pause, i)

    def restart_selected(self) -> None:
        ids = self.selected_ids()
        if ids and ask(self, "Tải lại từ đầu", f"Bỏ phần đã tải và tải lại {len(ids)} tệp từ đầu?")[0]:
            for i in ids:
                self.bridge.run(self.engine.restart, i)

    def delete_selected(self) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        ok, also_files = ask(self, "Xoá khỏi danh sách",
                             f"Xoá {len(ids)} mục khỏi danh sách tải?\nPhần tải dở (.tdpart) sẽ bị xoá.",
                             "Xoá luôn tệp đã tải xong trên ổ đĩa")
        if not ok:
            return
        for i in ids:
            pd = self.progress_dialogs.pop(i, None)
            if pd:
                pd.close()
            self.bridge.run(self.engine.remove, i, also_files)

    def delete_completed(self) -> None:
        done = [i for i, it in self.engine.snapshot["items"].items() if it["status"] == "completed"]
        if done and ask(self, "Xoá đã xong",
                        f"Xoá {len(done)} mục đã tải xong khỏi danh sách? (tệp vẫn giữ trên đĩa)")[0]:
            for i in done:
                self.bridge.run(self.engine.remove, i, False)

    def open_selected(self) -> None:
        for i in self.selected_ids()[:1]:
            it = self.bridge.item(i)
            if it and it["status"] == "completed":
                open_path(it["path"])

    def reveal_selected(self) -> None:
        for i in self.selected_ids()[:1]:
            it = self.bridge.item(i)
            if it:
                reveal_path(it["path"] if it["status"] == "completed" else it["path"] + ".tdpart")

    def props_selected(self) -> None:
        ids = self.selected_ids()
        if ids:
            PropertiesDialog(self.bridge, ids[0], self).exec()

    def copy_url(self) -> None:
        urls = [self.bridge.item(i)["url"] for i in self.selected_ids() if self.bridge.item(i)]
        text = "\n".join(urls)
        self._last_clip = text
        QGuiApplication.clipboard().setText(text)

    def _queue_selected(self, on: bool) -> None:
        for i in self.selected_ids():
            self.bridge.run(self.engine.set_queued, i, on)

    def _move_selected(self, delta: int) -> None:
        for i in self.selected_ids():
            self.bridge.run(self.engine.move_in_queue, i, delta)

    def limit_selected(self) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        it = self.bridge.item(ids[0])
        kb, ok = QInputDialog.getInt(self, "Giới hạn tốc độ", "KB/s cho tệp này (0 = không giới hạn):",
                                     it.get("speed_limit_kb", 0), 0, 10_000_000, 64)
        if ok:
            self.bridge.run(self.engine.set_speed_limit, ids[0], kb)

    def limit_global(self) -> None:
        kb, ok = QInputDialog.getInt(self, "Giới hạn tốc độ chung", "KB/s cho mọi tệp (0 = không giới hạn):",
                                     self.bridge.settings.global_speed_limit_kb, 0, 10_000_000, 64)
        if ok:
            self._set_global_limit(kb)

    def _set_global_limit(self, kb: int) -> None:
        self.bridge.run(self.engine.update_settings, {"global_speed_limit_kb": kb})
        self._ver = -1

    def paste_url(self) -> None:
        text = QApplication.clipboard().text().strip()
        lines = [ln.strip() for ln in text.splitlines() if URL_RE.match(ln.strip())]
        if len(lines) == 1:
            self.show_add_dialog(lines[0])
        elif len(lines) > 1:
            self.show_batch({"items": [{"url": u} for u in lines]})

    def import_list(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Nhập danh sách link", "",
                                              "Danh sách (*.txt *.ef2);;Tất cả (*.*)")
        if not path:
            return
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        items = parse_ef2(text) if "\n<" in "\n" + text and ">" in text else [
            {"url": ln.strip()} for ln in text.splitlines() if URL_RE.match(ln.strip())]
        if not items:
            QMessageBox.information(self, "Nhập danh sách", "Không tìm thấy link nào trong tệp.")
            return
        payload = {"items": items}
        if items and items[0].get("referer"):
            payload["referer"] = items[0]["referer"]
        self.show_batch(payload)

    def export_list(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Xuất danh sách link", "tdownload-links.txt", "Văn bản (*.txt)")
        if not path:
            return
        items = sorted(self.engine.snapshot["items"].values(), key=lambda i: i["created"])
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(i["url"] for i in items) + "\n")
        self.statusBar().showMessage(f"Đã xuất {len(items)} link ra {path}", 6000)

    def show_about(self) -> None:
        QMessageBox.about(self, "Giới thiệu TDownload", (
            f"<h3>TDownload {__version__}</h3>"
            "<p>Trình quản lý & tăng tốc tải xuống: chia đoạn động đa kết nối, tải tiếp sau khi mất mạng/tắt máy, "
            "hàng đợi, lịch hẹn, giới hạn tốc độ, tải video HLS, tải đồng thời từ nhiều nguồn, kiểm tra checksum, "
            "nhận link từ Chrome/Edge.</p>"
            "<p>Lấy cảm hứng từ cơ chế của Internet Download Manager, viết mới hoàn toàn bằng Python + Qt.</p>"
            "<p style='color:gray'>Chỉ tải nội dung bạn có quyền tải. TDownload không vượt DRM.</p>"))

    # ------------------------------------------------------------------ menu chuột phải / nhấp đúp
    def _context_menu(self, pos) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        m = QMenu(self)
        for a in (self.a_open, self.a_reveal, None, self.a_resume, self.a_pause, self.a_restart, None,
                  self.a_queue_add, self.a_queue_rm, self.a_up, self.a_down, None, self.a_limit, self.a_copy,
                  self.a_props, None, self.a_delete):
            m.addSeparator() if a is None else m.addAction(a)
        m.exec(self.view.viewport().mapToGlobal(pos))

    def _on_double_click(self, index) -> None:
        ident = self.proxy.index(index.row(), 0).data(ID_ROLE)
        it = self.bridge.item(ident)
        if not it:
            return
        if it["status"] == "completed":
            open_path(it["path"])
        else:
            self.show_progress(ident)

    # ------------------------------------------------------------------ sự kiện engine
    def on_event(self, kind: str, payload) -> None:
        if kind == "browser_add":
            self.show_add_dialog(payload.get("url", ""), payload)
        elif kind == "browser_batch":
            self.show_batch(payload)
        elif kind == "completed":
            self._on_completed(payload)
        elif kind == "error":
            if not self.isVisible() or self.isMinimized():
                self.tray.showMessage("Tải lỗi", f"{payload['filename']}: {payload['error']}",
                                      QSystemTrayIcon.MessageIcon.Warning, 6000)
        elif kind == "queue_finished":
            self._on_queue_finished(payload)
        elif kind == "message":
            self.statusBar().showMessage(str(payload), 8000)

    def _on_completed(self, d: dict) -> None:
        ident = d["id"]
        snap = self.bridge.item(ident) or {}
        item = {**snap, **{k: d[k] for k in ("filename", "size", "checksum_ok") if k in d},
                "path": os.path.join(d["save_dir"], d["filename"])}
        open_after = reveal_after = no_dialog = False
        pd = self.progress_dialogs.get(ident)
        if pd is not None:
            open_after, reveal_after, no_dialog = pd.completion_options()
            pd.close()
        if open_after:
            open_path(item["path"])
        if reveal_after:
            reveal_path(item["path"])
        self.tray.showMessage("Tải xong", item["filename"], icons.app_icon(), 4000)
        if self.bridge.settings.show_complete_dialog and not no_dialog and not open_after:
            dlg = CompleteDialog(item, None)
            dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

            def closed(*_):
                if dlg.again.isChecked():
                    self.bridge.run(self.engine.update_settings, {"show_complete_dialog": False})
            dlg.finished.connect(closed)
            self._keep(dlg)
            dlg.show()

    def _on_queue_finished(self, p: dict) -> None:
        self.statusBar().showMessage("Hàng đợi đã tải xong", 8000)
        action = p.get("after_done", "none")
        if not p.get("by_schedule") or action == "none":
            return
        labels = {"exit": "Thoát TDownload", "sleep": "Cho máy ngủ", "shutdown": "Tắt máy"}
        dlg = CountdownDialog(labels.get(action, action), 60, None)
        dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        if dlg.exec() != CountdownDialog.DialogCode.Accepted:
            return
        if action == "exit":
            self.quit_app()
        elif action == "shutdown" and sys.platform == "win32":
            subprocess.Popen(["shutdown", "/s", "/t", "30", "/c", "TDownload: hàng đợi đã xong"])
            self.quit_app()
        elif action == "sleep" and sys.platform == "win32":
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])

    # ------------------------------------------------------------------ clipboard & kéo thả
    def on_clipboard(self) -> None:
        if not self.bridge.settings.monitor_clipboard:
            return
        text = QApplication.clipboard().text().strip()
        if not text or text == self._last_clip or len(text) > 4096 or "\n" in text:
            return
        self._last_clip = text
        if not URL_RE.match(text):
            return
        ext = os.path.splitext(filename_from_url(text))[1].lower().lstrip(".")
        if ext in self.bridge.settings.capture_ext_set() or text.split("?", 1)[0].lower().endswith(".m3u8"):
            self.show_add_dialog(text)

    def dragEnterEvent(self, e) -> None:
        md = e.mimeData()
        if md.hasUrls() or (md.hasText() and "http" in md.text()):
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        md = e.mimeData()
        urls = [u.toString() for u in md.urls() if u.scheme() in ("http", "https")] if md.hasUrls() else []
        if not urls and md.hasText():
            urls = [ln.strip() for ln in md.text().splitlines() if URL_RE.match(ln.strip())]
        if len(urls) == 1:
            self.show_add_dialog(urls[0])
        elif urls:
            self.show_batch({"items": [{"url": u} for u in urls]})

    # ------------------------------------------------------------------ đóng / thoát
    def closeEvent(self, e) -> None:
        if not self.quitting and self.bridge.settings.minimize_to_tray and QSystemTrayIcon.isSystemTrayAvailable():
            e.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.showMessage("TDownload vẫn đang chạy", "Ứng dụng thu nhỏ xuống khay để tiếp tục tải và "
                                      "nhận link từ trình duyệt. Chuột phải biểu tượng → Thoát để tắt hẳn.",
                                      icons.app_icon(), 5000)
            return
        self.quit_app()
        e.accept()

    def quit_app(self) -> None:
        self.quitting = True
        for d in list(self.progress_dialogs.values()):
            d.close()
        self.tray.hide()
        QApplication.instance().quit()

"""Model bảng danh sách tải + bộ lọc theo nhóm/tìm kiếm."""

from __future__ import annotations

import datetime as dt
import os

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt

from ..core.util import fmt_eta, fmt_size, fmt_speed
from . import icons
from .widgets import PROGRESS_ROLE

ID_ROLE = Qt.ItemDataRole.UserRole + 2
SORT_ROLE = Qt.ItemDataRole.UserRole

COLUMNS = ["Tên tệp", "Kích thước", "Trạng thái", "Còn lại", "Tốc độ", "Lần thử cuối", "Mô tả"]


def fmt_time(ts: float) -> str:
    if not ts:
        return ""
    d = dt.datetime.fromtimestamp(ts)
    if d.date() == dt.date.today():
        return d.strftime("Hôm nay %H:%M")
    return d.strftime("%d/%m/%Y %H:%M")


class DownloadTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ids: list[str] = []
        self.items: dict[str, dict] = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.ids)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def update_from(self, items: dict[str, dict]) -> bool:
        """Trả về True nếu tập id thay đổi (cần reset)."""
        new_ids = sorted(items, key=lambda i: (items[i]["created"], i))
        if new_ids != self.ids:
            self.beginResetModel()
            self.ids = new_ids
            self.items = items
            self.endResetModel()
            return True
        self.items = items
        if self.ids:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.ids) - 1, len(COLUMNS) - 1))
        return False

    def item_at(self, row: int) -> dict | None:
        if 0 <= row < len(self.ids):
            return self.items.get(self.ids[row])
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        it = self.items.get(self.ids[index.row()])
        if it is None:
            return None
        col = index.column()
        if role == ID_ROLE:
            return it["id"]
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return it["filename"]
            if col == 1:
                return fmt_size(it["size"]) if it["size"] >= 0 else ""
            if col == 2:
                return it["status_text"]
            if col == 3:
                return fmt_eta(it["eta"]) if it["active"] else ""
            if col == 4:
                return fmt_speed(it["speed"]) if it["active"] else ""
            if col == 5:
                return fmt_time(it["last_try"] or it["created"])
            if col == 6:
                return it["description"] or it["error"] or it["message"]
        if role == SORT_ROLE:
            return [it["filename"].lower(), it["size"], it["progress"] or 0, it["eta"] or 1e12, it["speed"],
                    it["last_try"] or it["created"], it["description"]][col]
        if role == PROGRESS_ROLE and col == 2:
            return (it["progress"], it["status"], it["status_text"])
        if role == Qt.ItemDataRole.DecorationRole and col == 0:
            return icons.file_icon(os.path.splitext(it["filename"])[1].lower())
        if role == Qt.ItemDataRole.ToolTipRole:
            tip = [it["path"]]
            if it["error"]:
                tip.append("Lỗi: " + it["error"])
            elif it["message"]:
                tip.append(it["message"])
            return "\n".join(tip)
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (1, 4):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None


class DownloadFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.group = "all"
        self.text = ""
        self.setSortRole(SORT_ROLE)
        self.setDynamicSortFilter(True)

    def set_group(self, group: str) -> None:
        self.group = group
        self.invalidateFilter()

    def set_text(self, text: str) -> None:
        self.text = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        it = self.sourceModel().item_at(row)
        if it is None:
            return False
        g = self.group
        if g == "unfinished" and it["status"] == "completed":
            return False
        if g == "finished" and it["status"] != "completed":
            return False
        if g == "queue" and it["status"] != "queued":
            return False
        if g.startswith("cat:") and it["category"] != g[4:]:
            return False
        if self.text and self.text not in it["filename"].lower() and self.text not in it["url"].lower():
            return False
        return True

    def lessThan(self, left, right):
        a = left.data(SORT_ROLE)
        b = right.data(SORT_ROLE)
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)

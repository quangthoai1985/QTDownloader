"""Ghi song song vào một tệp duy nhất.

* Trên NTFS, tệp được đánh dấu *sparse* rồi đặt sẵn kích thước cuối: ghi ở offset bất kỳ
  không làm Windows phải điền số 0 cho khoảng trống phía trước (tránh khựng ở tệp nhiều GB),
  và không cần bước "ghép các phần" khi tải xong.
* Mỗi đoạn có chủ sở hữu riêng nên các lần ghi không chồng lấn; khoá chỉ để seek+write nguyên tử.
"""

from __future__ import annotations

import os
import sys
import threading

FSCTL_SET_SPARSE = 0x000900C4


def _set_sparse(f, sparse: bool = True) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        fn = k32.DeviceIoControl
        fn.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        fn.restype = wintypes.BOOL
        handle = msvcrt.get_osfhandle(f.fileno())
        returned = wintypes.DWORD(0)
        if sparse:
            ok = fn(handle, FSCTL_SET_SPARSE, None, 0, None, 0, ctypes.byref(returned), None)
        else:
            flag = ctypes.c_ubyte(0)  # FILE_SET_SPARSE_BUFFER{SetSparse = FALSE}
            ok = fn(handle, FSCTL_SET_SPARSE, ctypes.byref(flag), 1, None, 0, ctypes.byref(returned), None)
        return bool(ok)
    except (OSError, AttributeError, ValueError):
        return False


def mark_of_the_web(path: str, url: str, referer: str = "") -> bool:
    """Gắn Zone.Identifier như trình duyệt, để SmartScreen / Office Protected View vẫn cảnh báo
    tệp tải từ Internet (tải bằng trình quản lý tải không được "lách" lớp bảo vệ này)."""
    if sys.platform != "win32":
        return False
    from urllib.parse import urlsplit, urlunsplit

    def clean(u: str) -> str:  # bỏ user:pass trong URL
        try:
            p = urlsplit(u)
            return urlunsplit((p.scheme, p.hostname + (f":{p.port}" if p.port else ""), p.path, p.query, ""))
        except (ValueError, TypeError):
            return ""
    lines = ["[ZoneTransfer]", "ZoneId=3"]
    if referer and clean(referer):
        lines.append("ReferrerUrl=" + clean(referer))
    if clean(url):
        lines.append("HostUrl=" + clean(url))
    try:
        with open(path + ":Zone.Identifier", "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except OSError:  # ổ FAT32/exFAT không có luồng dữ liệu phụ
        return False


class PartFile:
    def __init__(self, path: str):
        self.path = path
        self._f = None
        self._lock = threading.Lock()
        self.sparse = False

    def open(self, size: int, fresh: bool) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        if fresh or not os.path.exists(self.path):
            self._f = open(self.path, "w+b", buffering=0)
            if size > 0:
                self.sparse = _set_sparse(self._f, True)
                self._f.truncate(size)
        else:
            self._f = open(self.path, "r+b", buffering=0)
            if size > 0 and os.path.getsize(self.path) != size:
                self._f.truncate(size)

    def write_at(self, offset: int, data: bytes) -> None:
        with self._lock:
            f = self._f
            if f is None:  # tệp đã đóng (tạm dừng) — bỏ lần ghi muộn, vị trí chưa được ghi nhận
                return
            f.seek(offset)
            view = memoryview(data)
            while view:
                n = f.write(view)
                view = view[n:]

    def truncate(self, size: int) -> None:
        with self._lock:
            if self._f is not None:
                self._f.truncate(size)

    def sync(self) -> None:
        with self._lock:
            if self._f is not None:
                os.fsync(self._f.fileno())

    def close(self, unsparse: bool = False) -> None:
        with self._lock:
            if self._f is None:
                return
            try:
                if unsparse and self.sparse:
                    _set_sparse(self._f, False)
                os.fsync(self._f.fileno())
            finally:
                self._f.close()
                self._f = None

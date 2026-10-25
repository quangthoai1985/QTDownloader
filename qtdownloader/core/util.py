"""Hàm tiện ích: định dạng kích thước/tốc độ, làm sạch tên tệp, đường dẫn duy nhất."""

from __future__ import annotations

import os
import re
import time
from urllib.parse import unquote, urlsplit

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def now() -> float:
    return time.time()


def fmt_size(n: int | float | None) -> str:
    if n is None or n < 0:
        return "?"
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(n)
    for u in units:
        if v < 1024 or u == units[-1]:
            if u == "B":
                return f"{int(v)} B"
            return f"{v:.2f} {u}" if v < 100 else f"{v:.1f} {u}"
        v /= 1024
    return f"{v:.1f} TB"


def fmt_speed(bps: float | None) -> str:
    if not bps or bps <= 0:
        return ""
    return fmt_size(bps) + "/s"


def fmt_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return ""
    s = int(seconds + 0.5)
    if s < 60:
        return f"{s} giây"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} phút {s:02d} giây"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h} giờ {m:02d} phút"
    d, h = divmod(h, 24)
    return f"{d} ngày {h} giờ"


def sanitize_filename(name: str, default: str = "download") -> str:
    name = (name or "").strip().replace("‮", "")  # chặn ký tự đảo chiều (giả mạo đuôi tệp)
    name = _INVALID.sub("_", name)
    name = name.rstrip(" .")
    if not name:
        name = default
    stem = name.split(".")[0].upper()
    if stem in _RESERVED:
        name = "_" + name
    if len(name) > 180:
        root, ext = os.path.splitext(name)
        name = root[: 180 - len(ext)] + ext
    return name


def filename_from_url(url: str) -> str:
    path = urlsplit(url).path
    base = unquote(path.rstrip("/").rsplit("/", 1)[-1]) if path else ""
    return sanitize_filename(base) if base else ""


def unique_path(directory: str, filename: str, taken: set[str] | None = None) -> str:
    """Trả về tên tệp chưa tồn tại trong thư mục (thêm ' (1)', ' (2)' …)."""
    taken = {t.lower() for t in (taken or set())}
    root, ext = os.path.splitext(filename)
    candidate = filename
    i = 1
    while (
        os.path.exists(os.path.join(directory, candidate))
        or os.path.exists(os.path.join(directory, candidate + ".tdpart"))
        or os.path.join(directory, candidate).lower() in taken
    ):
        candidate = f"{root} ({i}){ext}"
        i += 1
    return candidate


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


_BATCH = re.compile(r"\[(\d+)-(\d+)\]|\[([a-zA-Z])-([a-zA-Z])\]")


def expand_batch_pattern(pattern: str, limit: int = 10000) -> list[str]:
    """Mở rộng mẫu kiểu IDM: http://x/file[001-120].zip, http://x/[a-z].jpg."""
    m = _BATCH.search(pattern)
    if not m:
        return [pattern]
    out: list[str] = []
    head, tail = pattern[: m.start()], pattern[m.end():]
    if m.group(1) is not None:
        a, b = m.group(1), m.group(2)
        width = len(a) if a.startswith("0") or len(a) == len(b) else 0
        lo, hi = int(a), int(b)
        step = 1 if hi >= lo else -1
        values = [str(i).zfill(width) for i in range(lo, hi + step, step)]
    else:
        lo, hi = ord(m.group(3)), ord(m.group(4))
        step = 1 if hi >= lo else -1
        values = [chr(c) for c in range(lo, hi + step, step)]
    for v in values:
        for rest in expand_batch_pattern(tail, limit):
            out.append(head + v + rest)
            if len(out) >= limit:
                return out
    return out

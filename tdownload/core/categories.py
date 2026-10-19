"""Phân loại tệp theo đuôi (giống cách IDM chia Compressed/Documents/Music/…)."""

from __future__ import annotations

import os

# key nội bộ -> (tên hiển thị, thư mục con, đuôi tệp)
CATEGORIES: dict[str, tuple[str, str, set[str]]] = {
    "compressed": ("Tệp nén", "Compressed", {
        "zip", "rar", "7z", "gz", "tgz", "bz2", "xz", "tar", "zst", "lz", "lzma", "cab", "arj", "z", "iso", "img",
    }),
    "documents": ("Tài liệu", "Documents", {
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "txt", "rtf", "csv", "epub",
        "mobi", "djvu", "md", "xml", "json",
    }),
    "music": ("Âm nhạc", "Music", {
        "mp3", "wav", "flac", "aac", "m4a", "ogg", "oga", "opus", "wma", "aiff", "ape", "mid", "midi",
    }),
    "programs": ("Chương trình", "Programs", {
        "exe", "msi", "msix", "appx", "apk", "xapk", "dmg", "pkg", "deb", "rpm", "appimage", "bat", "jar",
    }),
    "video": ("Video", "Video", {
        "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "mpg", "mpeg", "3gp", "ts", "m2ts", "vob",
        "ogv", "rmvb",
    }),
    "general": ("Khác", "General", set()),
}

ORDER = ["compressed", "documents", "music", "programs", "video", "general"]


def category_for(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if not ext:
        return "general"
    for key in ORDER:
        if ext in CATEGORIES[key][2]:
            return key
    return "general"


def display_name(key: str) -> str:
    return CATEGORIES.get(key, CATEGORIES["general"])[0]


def subdir(key: str) -> str:
    return CATEGORIES.get(key, CATEGORIES["general"])[1]


def all_extensions() -> set[str]:
    s: set[str] = set()
    for _, _, exts in CATEGORIES.values():
        s |= exts
    return s

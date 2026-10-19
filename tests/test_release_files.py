"""Giấy phép MIT, thông báo thư viện bên thứ ba, và repo không chứa tư liệu dịch ngược phần mềm khác."""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def read(*p: str) -> str:
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def test_license_is_mit():
    text = read("LICENSE")
    assert text.startswith("MIT License")
    assert "Permission is hereby granted, free of charge" in text


def test_notices_cover_every_license_file():
    notices = read("THIRD_PARTY_NOTICES.md")
    files = sorted(os.listdir(os.path.join(ROOT, "licenses")))
    assert files
    for name in files:
        assert f"`{name}`" in notices, f"{name} chưa được nhắc trong THIRD_PARTY_NOTICES.md"
        assert os.path.getsize(os.path.join(ROOT, "licenses", name)) > 500
    for name in re.findall(r"`([\w.-]+\.txt)`", notices):
        assert name in files, f"THIRD_PARTY_NOTICES.md nhắc {name} nhưng licenses/ không có"
    # thư viện chạy thật trong requirements.txt phải có trong bảng
    for pkg in ("PySide6", "httpx", "h2"):
        assert pkg in notices


def test_release_package_ships_notices():
    import package_release
    arcs = [arc for _src, arc in package_release.notice_files()]
    assert arcs[:2] == ["LICENSE.txt", "THIRD_PARTY_NOTICES.md"]
    assert "licenses/Qt-PySide6-LGPL-3.0.txt" in arcs
    assert all(os.path.isfile(src) for src, _arc in package_release.notice_files())


def test_no_reverse_engineering_material():
    """Dự án chỉ dựa trên chuẩn công khai: không đưa dump/ký hiệu nội bộ của phần mềm khác vào repo."""
    banned = re.compile("|".join(["IDM" + "an", "Ghid" + "ra", "xre" + "fs", "feasib" + "ility",
                                  "IDMMsg" + "Host", "Chunks" + "List", "tonec" + r"\.idm"]), re.I)
    skip_dirs = {".git", "build", "dist", "release", "licenses", "__pycache__", ".pytest_cache", "assets"}
    hits = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.endswith(".tdhls")]
        for fn in files:
            if not fn.endswith((".py", ".md", ".js", ".json", ".html", ".css", ".txt", ".bat", ".mjs", ".gitignore")):
                continue
            path = os.path.join(base, fn)
            with open(path, encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    if banned.search(line):
                        hits.append(f"{os.path.relpath(path, ROOT)}:{i}")
    assert not hits, hits

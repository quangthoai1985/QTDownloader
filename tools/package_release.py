"""Đóng gói các tệp đính kèm GitHub Release vào thư mục release/.

    python tools/package_release.py [--dist THƯ_MỤC]   (chạy sau build.bat; mặc định dist)

Tạo:
  TDownload-<ver>-win64.zip          thư mục dist\\TDownload (giải nén là chạy TDownload.exe)
                                     + LICENSE.txt, THIRD_PARTY_NOTICES.md, licenses\\ (giấy phép thư viện kèm theo)
  TDownload-extension-<ver>.zip      extension (giải nén rồi "Tải tiện ích đã giải nén") + LICENSE.txt
  SHA256SUMS.txt
"""

import argparse
import hashlib
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tdownload import __version__  # noqa: E402


def notice_files() -> list[tuple[str, str]]:
    """(tệp nguồn, tên trong gói) — giấy phép MIT của dự án + giấy phép các thư viện đóng kèm .exe."""
    files = [(os.path.join(ROOT, "LICENSE"), "LICENSE.txt"),
             (os.path.join(ROOT, "THIRD_PARTY_NOTICES.md"), "THIRD_PARTY_NOTICES.md")]
    lic = os.path.join(ROOT, "licenses")
    files += [(os.path.join(lic, n), f"licenses/{n}") for n in sorted(os.listdir(lic))]
    return files


def zip_dir(src: str, dest: str, prefix: str, extra: list[tuple[str, str]]) -> None:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, _dirs, files in os.walk(src):
            for fn in sorted(files):
                full = os.path.join(base, fn)
                rel = os.path.relpath(full, src)
                z.write(full, os.path.join(prefix, rel) if prefix else rel)
        for full, arc in extra:
            z.write(full, f"{prefix}/{arc}" if prefix else arc)


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default=os.path.join(ROOT, "dist"), help="thư mục distpath đã dùng khi build")
    dist = os.path.join(os.path.abspath(ap.parse_args().dist), "TDownload")
    ext = os.path.join(ROOT, "extension")
    out_dir = os.path.join(ROOT, "release")
    if not os.path.isfile(os.path.join(dist, "TDownload.exe")):
        raise SystemExit(f"Chưa có {dist}\\TDownload.exe — chạy build.bat trước")
    with open(os.path.join(ext, "manifest.json"), encoding="utf-8") as f:
        ext_ver = json.load(f)["version"]
    if ext_ver != __version__:
        raise SystemExit(f"Lệch phiên bản: app {__version__} ≠ extension {ext_ver}")

    os.makedirs(out_dir, exist_ok=True)
    for name in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, name))

    app_zip = os.path.join(out_dir, f"TDownload-{__version__}-win64.zip")
    ext_zip = os.path.join(out_dir, f"TDownload-extension-{__version__}.zip")
    zip_dir(dist, app_zip, "TDownload", notice_files())
    zip_dir(ext, ext_zip, "", notice_files()[:1])

    lines = []
    for path in (app_zip, ext_zip):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(1 << 20):
                h.update(chunk)
        lines.append(f"{h.hexdigest()}  {os.path.basename(path)}")
        print(f"{os.path.basename(path)}  {os.path.getsize(path) / 1048576:.1f} MB")
    with open(os.path.join(out_dir, "SHA256SUMS.txt"), "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

"""Đóng gói các tệp đính kèm GitHub Release vào thư mục release/.

    python tools/package_release.py [--dist THƯ_MỤC]   (chạy sau build.bat; mặc định dist)

Tạo:
  TDownload-<ver>-win64.zip          thư mục dist\\TDownload (giải nén là chạy TDownload.exe)
  TDownload-extension-<ver>.zip      extension (giải nén rồi "Tải tiện ích đã giải nén")
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


def zip_dir(src: str, dest: str, prefix: str) -> None:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, _dirs, files in os.walk(src):
            for fn in sorted(files):
                full = os.path.join(base, fn)
                rel = os.path.relpath(full, src)
                z.write(full, os.path.join(prefix, rel) if prefix else rel)


app_zip = os.path.join(out_dir, f"TDownload-{__version__}-win64.zip")
ext_zip = os.path.join(out_dir, f"TDownload-extension-{__version__}.zip")
zip_dir(dist, app_zip, "TDownload")
zip_dir(ext, ext_zip, "")

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

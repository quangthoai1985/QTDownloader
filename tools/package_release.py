"""Đóng gói các tệp đính kèm GitHub Release vào thư mục release/.

    python tools/package_release.py [--dist THƯ_MỤC] [--no-installer]   (chạy sau build.bat; mặc định dist)

Tạo:
  QTDownloader-<ver>-setup.exe          bộ cài Inno Setup (installer.iss): cài theo người dùng, không cần UAC,
                                        có trong Cài đặt › Ứng dụng để gỡ; bản đã cài tự cập nhật bằng tệp này
  QTDownloader-<ver>-win64.zip          thư mục dist\\QTDownloader (giải nén là chạy QTDownloader.exe)
                                        + LICENSE.txt, THIRD_PARTY_NOTICES.md, licenses\\ (giấy phép thư viện kèm theo)
  TDownload-<ver>-win64.zip             bản sao của gói trên với TÊN CŨ — bản TDownload ≤ 1.0.3 chỉ nhận tên này
  QTDownloader-extension-<ver>.zip      extension (giải nén rồi "Tải tiện ích đã giải nén") + LICENSE.txt
  SHA256SUMS.txt                        trình cập nhật dựa vào tệp này để kiểm toàn vẹn — phải liệt kê mọi tệp trên

Bộ cài cần Inno Setup 6 (ISCC.exe): tìm trong PATH, %LOCALAPPDATA%\\Programs\\Inno Setup 6, Program Files.
Chưa có thì cài: winget install --id JRSoftware.InnoSetup -e --scope user
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from qtdownloader import APP_ID, __version__  # noqa: E402

LEGACY_ZIP_PREFIX = "TDownload"   # tên gói mà bản ≤ 1.0.3 (core/updater.py cũ) tìm trong Release


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


def find_iscc() -> str | None:
    candidates = [shutil.which("iscc"), shutil.which("ISCC.exe")]
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            sub = os.path.join("Programs", "Inno Setup 6") if base == os.environ.get("LOCALAPPDATA") else "Inno Setup 6"
            candidates.append(os.path.join(base, sub, "ISCC.exe"))
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def build_installer(dist: str, out_dir: str) -> str:
    iscc = find_iscc()
    if not iscc:
        raise SystemExit("Không tìm thấy Inno Setup 6 (ISCC.exe). Cài: winget install --id JRSoftware.InnoSetup -e "
                         "--scope user — hoặc chạy với --no-installer để chỉ tạo gói zip.")
    subprocess.run([iscc, "/Qp", f"/DAppVersion={__version__}", f"/DSourceDir={dist}", f"/DOutputDir={out_dir}",
                    os.path.join(ROOT, "installer.iss")], cwd=ROOT, check=True)
    setup = os.path.join(out_dir, f"{APP_ID}-{__version__}-setup.exe")
    if not os.path.isfile(setup):
        raise SystemExit(f"ISCC chạy xong nhưng không thấy {setup}")
    return setup


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default=os.path.join(ROOT, "dist"), help="thư mục distpath đã dùng khi build")
    ap.add_argument("--no-installer", action="store_true", help="không biên dịch bộ cài (máy chưa có Inno Setup)")
    args = ap.parse_args()
    dist = os.path.join(os.path.abspath(args.dist), APP_ID)
    ext = os.path.join(ROOT, "extension")
    out_dir = os.path.join(ROOT, "release")
    if not os.path.isfile(os.path.join(dist, f"{APP_ID}.exe")):
        raise SystemExit(f"Chưa có {dist}\\{APP_ID}.exe — chạy build.bat trước")
    with open(os.path.join(ext, "manifest.json"), encoding="utf-8") as f:
        ext_ver = json.load(f)["version"]
    if ext_ver != __version__:
        raise SystemExit(f"Lệch phiên bản: app {__version__} ≠ extension {ext_ver}")

    os.makedirs(out_dir, exist_ok=True)
    for name in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, name))

    app_zip = os.path.join(out_dir, f"{APP_ID}-{__version__}-win64.zip")
    legacy_zip = os.path.join(out_dir, f"{LEGACY_ZIP_PREFIX}-{__version__}-win64.zip")
    ext_zip = os.path.join(out_dir, f"{APP_ID}-extension-{__version__}.zip")
    zip_dir(dist, app_zip, APP_ID, notice_files())
    shutil.copyfile(app_zip, legacy_zip)
    zip_dir(ext, ext_zip, "", notice_files()[:1])
    outputs = [app_zip, legacy_zip, ext_zip]
    if not args.no_installer:
        outputs.insert(0, build_installer(dist, out_dir))

    lines = []
    for path in outputs:
        lines.append(f"{sha256_of(path)}  {os.path.basename(path)}")
        print(f"{os.path.basename(path)}  {os.path.getsize(path) / 1048576:.1f} MB")
    with open(os.path.join(out_dir, "SHA256SUMS.txt"), "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

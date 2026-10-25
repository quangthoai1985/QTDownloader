"""Sinh assets/version_info.txt (tài nguyên phiên bản Windows cho PyInstaller) từ qtdownloader.__version__.

Nhờ đó chuột phải QTDownloader.exe → Properties → Details hiện đúng số phiên bản.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from qtdownloader import APP_ID, APP_NAME, __version__  # noqa: E402

m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", __version__)
if not m:
    raise SystemExit(f"__version__ phải dạng MAJOR.MINOR.PATCH, đang là {__version__!r}")
nums = tuple(int(x) for x in m.groups()) + (0,)

TEMPLATE = """# -*- coding: utf-8 -*-
VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('042A04B0', [
      StringStruct('CompanyName', '{app}'),
      StringStruct('FileDescription', '{app} - Trình tăng tốc tải xuống'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', '{exe}'),
      StringStruct('OriginalFilename', '{exe}.exe'),
      StringStruct('ProductName', '{app}'),
      StringStruct('ProductVersion', '{ver}'),
    ])]),
    VarFileInfo([VarStruct('Translation', [0x042A, 1200])]),
  ]
)
"""

out = os.path.join(ROOT, "assets", "version_info.txt")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write(TEMPLATE.format(nums=nums, ver=__version__, app=APP_NAME, exe=APP_ID))
print("version", __version__, "->", out)

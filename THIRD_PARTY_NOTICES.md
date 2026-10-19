# Thông báo giấy phép của thành phần bên thứ ba

Mã nguồn TDownload phát hành theo giấy phép [MIT](LICENSE). Bản đóng gói `TDownload.exe` (PyInstaller) có kèm các
thành phần dưới đây, mỗi thành phần giữ giấy phép riêng; văn bản đầy đủ nằm trong thư mục [`licenses/`](licenses/).
Phiên bản ghi theo bản phát hành gần nhất; chạy từ mã nguồn thì dùng bản `pip` đã cài.

| Thành phần | Phiên bản | Giấy phép | Văn bản | Mã nguồn |
|---|---|---|---|---|
| Qt for Python (PySide6, Shiboken6) và thư viện Qt 6 | 6.11.2 | LGPL-3.0 | `Qt-PySide6-LGPL-3.0.txt`, `GPL-3.0.txt` | https://download.qt.io/official_releases/QtForPython/ · https://download.qt.io/official_releases/qt/ |
| Python (trình thông dịch và thư viện chuẩn, kèm OpenSSL, libffi, SQLite, zlib, bzip2, xz… theo bản Windows) | 3.14 | PSF-2.0 (và các giấy phép ghi trong tệp) | `Python-PSF-2.0.txt` | https://www.python.org/downloads/source/ |
| httpx | 0.28.1 | BSD-3-Clause | `httpx-BSD-3-Clause.txt` | https://github.com/encode/httpx |
| httpcore | 1.0.9 | BSD-3-Clause | `httpcore-BSD-3-Clause.txt` | https://github.com/encode/httpcore |
| h11 | 0.16.0 | MIT | `h11-MIT.txt` | https://github.com/python-hyper/h11 |
| h2 | 4.3.0 | MIT | `h2-MIT.txt` | https://github.com/python-hyper/h2 |
| hpack | 4.1.0 | MIT | `hpack-MIT.txt` | https://github.com/python-hyper/hpack |
| hyperframe | 6.1.0 | MIT | `hyperframe-MIT.txt` | https://github.com/python-hyper/hyperframe |
| anyio | 4.12.1 | MIT | `anyio-MIT.txt` | https://github.com/agronholm/anyio |
| idna | 3.11 | BSD-3-Clause | `idna-BSD-3-Clause.txt` | https://github.com/kjd/idna |
| certifi (bộ chứng thư gốc của Mozilla) | 2026.1.4 | MPL-2.0 | `certifi-MPL-2.0.txt` | https://github.com/certifi/python-certifi |
| packaging | 26.0 | BSD-2-Clause (lựa chọn trong cặp Apache-2.0 OR BSD-2-Clause) | `packaging-BSD-2-Clause.txt` | https://github.com/pypa/packaging |
| typing_extensions | 4.15.0 | PSF-2.0 | `typing_extensions-PSF-2.0.txt` | https://github.com/python/typing_extensions |

## Ghi chú về Qt / PySide6 (LGPL-3.0)

- TDownload dùng Qt và PySide6 **nguyên bản, không sửa đổi**, liên kết động: các tệp `Qt6*.dll`, `pyside6*.dll`,
  `shiboken6*.dll` nằm riêng trong thư mục `_internal\PySide6` của gói. Bạn có quyền thay chúng bằng một bản Qt/PySide6
  tương thích khác (kể cả bản tự biên dịch) mà không cần mã nguồn của TDownload — dù mã nguồn TDownload vẫn công khai
  theo MIT.
- Mã nguồn tương ứng của Qt/PySide6 lấy tại các địa chỉ trong bảng, đúng phiên bản ghi ở trên.

## Thành phần khác trong gói

- **PyInstaller bootloader** (GPL-2.0-or-later kèm ngoại lệ cho phép phân phối chương trình đóng gói theo giấy phép
  bất kỳ) — https://github.com/pyinstaller/pyinstaller.
- **Microsoft Visual C++ Runtime / Universal CRT** (`VCRUNTIME140*.dll`, `api-ms-win-*.dll`, `ucrtbase.dll`) —
  phân phối lại theo điều khoản tệp phân phối lại của Microsoft.
- Icon của TDownload do dự án tự vẽ (`tdownload/ui/icons.py`, `tools/make_icons.py`), theo giấy phép MIT của dự án.

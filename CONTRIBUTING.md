# Đóng góp cho TDownload

Cảm ơn bạn quan tâm! Ai cũng có thể đóng góp: báo lỗi, đề xuất tính năng, sửa tài liệu, dịch, thử trên máy chủ thật
hay gửi mã. Hãy đọc [Quy tắc ứng xử](CODE_OF_CONDUCT.md) trước khi tham gia.

## Báo lỗi và đề xuất

- Mở [issue mới](../../issues/new/choose) theo mẫu. Với lỗi, ghi rõ phiên bản TDownload (Trợ giúp → Giới thiệu),
  phiên bản Windows, trình duyệt, các bước tái hiện.
- Nhật ký nằm ở `%LOCALAPPDATA%\TDownload\logs\tdownload.log` — **xoá cookie, token, link riêng tư** trước khi dán.
- Lỗ hổng bảo mật: **không** mở issue công khai, xem [SECURITY.md](SECURITY.md).
- Việc cần người giúp nhất hiện nay: thử tải từ các máy chủ thật (Google Drive, Fshare, Mediafire, CDN…) và báo kết
  quả — xem [CLAUDE.md §7](CLAUDE.md#7-việc-cần-làm-tiếp-theo-thứ-tự-ưu-tiên).

## Chuẩn bị môi trường

- Windows 10/11, Python 3.11 trở lên (dự án phát triển trên 3.14), Node.js (tuỳ chọn, để kiểm extension).

```bash
python -m pip install -r requirements.txt
python -m tdownload                 # chạy giao diện
python -m pytest -q tests           # bộ kiểm thử (~70 giây)
python tests/server.py --port 8765  # máy chủ thử nghiệm để bấm thử trên giao diện
build.bat [thư_mục]                 # đóng gói TDownload.exe (PyInstaller)
```

Khi thử nghiệm, đặt biến môi trường `TDOWNLOAD_DATA` trỏ tới một thư mục tạm để không đụng dữ liệu thật. Kiến trúc,
quy ước và những "bẫy" đã gặp được ghi trong [CLAUDE.md](CLAUDE.md); thiết kế engine trong
[docs/THIET_KE.md](docs/THIET_KE.md).

## Quy ước

- Chuỗi giao diện và tài liệu viết **tiếng Việt có dấu**.
- Engine (`tdownload/core/`) chạy trên một vòng lặp asyncio riêng: không chặn event loop; I/O tệp qua
  `engine.io_pool`. Giao diện chỉ gọi engine qua `engine.call(...)` và đọc `engine.snapshot`.
- Lỗi báo cho người dùng dùng `DownloadError("…tiếng Việt…")`.
- Tệp `.bat` phải ASCII + xuống dòng CRLF.
- Sửa extension: chạy `node --check extension/*.js`.
- Thêm test cho hành vi mới (dùng fixture `engine`/`srv` trong `tests/conftest.py`); test không được ghi vào dữ liệu
  hay registry thật.

## Nguồn gốc mã

- Chỉ cài đặt từ **chuẩn công khai** (RFC…) và **hành vi quan sát được từ bên ngoài**. Không gửi mã, chuỗi, icon hay
  tài liệu có được từ việc dịch ngược phần mềm khác, hoặc chép từ dự án có giấy phép không tương thích MIT.
- Dùng lại mã MIT/BSD/Apache của người khác thì giữ thông báo bản quyền và ghi nguồn.
- Thêm thư viện vào gói `.exe` thì cập nhật [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) và thư mục `licenses/`.

## Gửi Pull Request

1. Fork repo, tạo nhánh từ `main` (vd `sua-loi-tai-tiep`).
2. Commit nhỏ, thông điệp rõ ràng (tiếng Việt hoặc tiếng Anh đều được).
3. `python -m pytest -q tests` qua hết; thay đổi giao diện thì kèm ảnh chụp.
4. Thêm một dòng vào mục `## [Chưa phát hành]` của [CHANGELOG.md](CHANGELOG.md).
5. Mở PR, mô tả thay đổi và cách đã thử.

## Giấy phép

TDownload dùng giấy phép [MIT](LICENSE). Khi gửi đóng góp, bạn đồng ý phát hành phần đóng góp đó theo cùng giấy phép
MIT và xác nhận mình có quyền làm vậy.

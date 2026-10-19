# TDownload

Trình quản lý & tăng tốc tải xuống cho Windows, mô phỏng cơ chế của Internet Download Manager
(chia đoạn động đa kết nối, tải tiếp, hàng đợi, lịch hẹn, bắt link từ trình duyệt) — viết mới hoàn toàn
bằng Python + Qt.

- Thiết kế engine tải: [docs/THIET_KE.md](docs/THIET_KE.md)
- Đề xuất tính năng tiếp theo: [docs/DE_XUAT_TINH_NANG.md](docs/DE_XUAT_TINH_NANG.md)
- Lịch sử thay đổi: [CHANGELOG.md](CHANGELOG.md) · Bàn giao cho lập trình viên/Agent: [CLAUDE.md](CLAUDE.md)

## Tính năng

| Nhóm | Có gì |
|---|---|
| Tăng tốc | 1–32 kết nối/tệp, **chia đoạn động** (kết nối xong lấy nửa sau đoạn lớn nhất, tái dùng keep-alive), cửa sổ yêu cầu thích nghi, tự giảm kết nối khi server giới hạn (429/503) |
| Nhiều nguồn | Tải **đồng thời** từ nhiều mirror của cùng một tệp |
| Tải tiếp | Tạm dừng / mất mạng / tắt máy → tải tiếp đúng byte (SQLite + fsync), kiểm ETag/If-Range, "Cập nhật địa chỉ tải" cho link hết hạn |
| Quản lý | Phân loại theo đuôi tệp, hàng đợi (số tệp đồng thời), lịch hẹn giờ bắt đầu/dừng, tắt máy/ngủ khi xong, tải hàng loạt `file[001-100].zip`, nhập `.txt`/`.ef2` của IDM |
| Tốc độ | Giới hạn chung + riêng từng tệp, đổi ngay khi đang tải |
| Video | Tải HLS `.m3u8` (chọn chất lượng, tải song song đoạn, ghép `.ts`/`.mp4`; có ffmpeg thì remux MP4). Từ chối luồng có DRM |
| An toàn | Kiểm checksum (tự tìm `.sha256`), Mark-of-the-Web, cảnh báo "server trả trang web", kiểm dung lượng ổ trước khi tải |
| Trình duyệt | Extension Chrome/Edge/Cốc Cốc: tự chuyển tải xuống, menu chuột phải, tải tất cả/đã chọn liên kết, phát hiện video trên tab |
| Cập nhật | Tự phát hiện bản mới trên GitHub Releases (1 lần/ngày hoặc Trợ giúp → Kiểm tra bản mới), tải gói mới kèm kiểm SHA-256 |
| Giao diện | Tiếng Việt, cửa sổ tiến trình hiện từng kết nối + đồ thị tốc độ, khay hệ thống, theo dõi clipboard, kéo-thả link |

## Chạy

Yêu cầu: Windows 10/11, Python 3.11+.

```bash
python -m pip install -r requirements.txt
```

```bash
python -m tdownload
```

Hoặc bấm đúp `run.bat`. Đóng cửa sổ thì app thu xuống khay; muốn tắt hẳn: chuột phải icon khay → **Thoát**.

Bản đóng gói không cần Python: tải `TDownload-<phiên bản>-win64.zip` ở mục **Releases** của repo, giải nén, chạy
`TDownload\TDownload.exe` (chưa ký số nên Windows SmartScreen có thể cảnh báo → *More info → Run anyway*).
Tự build: `build.bat` → `dist\TDownload\TDownload.exe`.

### Dòng lệnh (không giao diện)

```bash
python -m tdownload.cli "https://example.com/file.iso" -c 16 -o D:\Downloads
```

Tham số: `-c` số kết nối, `-l` giới hạn KB/s, `--mirror URL` nguồn phụ (lặp được), `--checksum sha256:…`.

## Cài extension trình duyệt

1. Mở `chrome://extensions` (Edge: `edge://extensions`, Cốc Cốc: `coccoc://extensions`).
2. Bật **Chế độ dành cho nhà phát triển** → **Tải tiện ích đã giải nén** → chọn thư mục `extension`.
3. Mở TDownload. Biểu tượng extension báo "đã kết nối" là xong.

Khi TDownload không chạy, trình duyệt tự tải như bình thường. Tắt tạm hoặc bỏ qua một trang ngay trong popup
của extension.

## Cấu trúc

```
tdownload/core/     engine, không phụ thuộc giao diện
  segments.py       thuật toán chia đoạn động
  http_task.py      tải 1 tệp: worker, cửa sổ yêu cầu, retry, checkpoint, checksum
  hls.py            tải luồng HLS
  engine.py         hàng đợi, lịch, giới hạn tốc độ, snapshot cho UI
  api_server.py     API 127.0.0.1 cho extension
  fileio.py         ghi song song vào tệp sparse, Mark-of-the-Web
tdownload/ui/       giao diện PySide6
extension/          extension Manifest V3
tests/              máy chủ thử nghiệm + 32 test (pytest)
```

Dữ liệu (danh sách tải, cài đặt, log) nằm ở `%LOCALAPPDATA%\TDownload`. Đặt biến `TDOWNLOAD_DATA` để dùng thư mục khác.

## Kiểm thử

```bash
python -m pytest -q tests
```

Bộ test chạy một máy chủ HTTP cục bộ mô phỏng: giới hạn tốc độ mỗi kết nối, không hỗ trợ Range, không có
Content-Length, rớt kết nối ngẫu nhiên, giới hạn số kết nối (503), phản hồi Range bị cắt ngắn, tệp thay đổi
trên server, chuyển hướng, Content-Disposition tiếng Việt, HLS thường/mã hoá/live.

Xem thử máy chủ đó bằng giao diện: `python tests/server.py` rồi thêm link
`http://127.0.0.1:8765/file/test.bin?size=50000000&rate=800` (800 KB/s mỗi kết nối).

## Lưu ý

- Tốc độ tăng chỉ khi máy chủ hỗ trợ Range và giới hạn theo từng kết nối; server giới hạn theo IP thì đa kết nối không giúp.
- Chỉ tải nội dung bạn có quyền tải. TDownload không vượt DRM và không dùng mã, icon hay thương hiệu của IDM.

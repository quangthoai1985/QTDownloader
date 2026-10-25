# QT Downloader

> Trước bản 1.1.0 dự án tên **TDownload** (repo `quangthoai1985/TDownload`). Mở bản mới lần đầu, danh sách tải
> và thiết lập ở `%LOCALAPPDATA%\TDownload` được tự chuyển sang `%LOCALAPPDATA%\QTDownloader`.

Trình quản lý & tăng tốc tải xuống cho Windows theo kiểu Internet Download Manager (chia đoạn động đa kết nối,
tải tiếp, hàng đợi, lịch hẹn, bắt link từ trình duyệt) — mã nguồn mở, viết bằng Python + Qt.
Giấy phép [MIT](LICENSE) — ai cũng có thể dùng, sửa và [đóng góp](CONTRIBUTING.md).

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
| Cài đặt & cập nhật | Bộ cài theo người dùng (không cần quyền quản trị), gỡ trong Cài đặt › Ứng dụng. Mỗi lần mở app tự hỏi GitHub Releases; bản đã cài tự tải ngầm bộ cài mới (kiểm SHA-256) → **Khởi động lại để cập nhật**, không bấm thì tự cài khi thoát app |
| Giao diện | Tiếng Việt, cửa sổ tiến trình hiện từng kết nối + đồ thị tốc độ, khay hệ thống, theo dõi clipboard, kéo-thả link |

## Chạy

Yêu cầu: Windows 10/11, Python 3.11+.

```bash
python -m pip install -r requirements.txt
```

```bash
python -m qtdownloader
```

Hoặc bấm đúp `run.bat`. Đóng cửa sổ thì app thu xuống khay; muốn tắt hẳn: chuột phải icon khay → **Thoát**.

### Cài đặt (không cần Python)

Tải `QTDownloader-<phiên bản>-setup.exe` ở mục **Releases** của repo rồi chạy. Bộ cài:

- cài vào `%LOCALAPPDATA%\Programs\QT Downloader`, **không cần quyền quản trị** (không hỏi UAC);
- tạo lối tắt trong menu Start (tuỳ chọn thêm lối tắt màn hình nền);
- đăng ký với Windows → gỡ được trong **Cài đặt › Ứng dụng › Ứng dụng đã cài** (hoặc Control Panel). Trình gỡ cài đặt
  xoá cả khoá giao thức `qtdownloader://` và mục khởi động cùng Windows nếu bạn đã bật, rồi hỏi có xoá danh sách tải
  và thiết lập không (tệp đã tải về không bao giờ bị xoá);
- cài im lặng: `QTDownloader-<ver>-setup.exe /VERYSILENT /SUPPRESSMSGBOXES`.

Bản cài tự cập nhật: mỗi lần mở app sẽ hỏi GitHub, có bản mới thì báo ngay và tải ngầm bộ cài, xong hiện nút
**Khởi động lại để cập nhật** ở thanh trạng thái (không bấm thì bản mới tự cài khi bạn thoát app). Tắt trong
**Tuỳ chọn → Chung**.

Bản giải nén (portable): `QTDownloader-<phiên bản>-win64.zip`, giải nén rồi chạy `QTDownloader\QTDownloader.exe` —
bản này chỉ được báo có bản mới. Chưa ký số nên Windows SmartScreen có thể cảnh báo → *More info → Run anyway*.

Tự build: `build.bat` → `dist\QTDownloader\QTDownloader.exe`; đóng gói phát hành kèm bộ cài (cần
[Inno Setup 6](https://jrsoftware.org/isinfo.php)): `python tools/package_release.py` → `release\`.

### Dòng lệnh (không giao diện)

```bash
python -m qtdownloader.cli "https://example.com/file.iso" -c 16 -o D:\Downloads
```

Tham số: `-c` số kết nối, `-l` giới hạn KB/s, `--mirror URL` nguồn phụ (lặp được), `--checksum sha256:…`.

## Cài extension trình duyệt

1. Mở `chrome://extensions` (Edge: `edge://extensions`, Cốc Cốc: `coccoc://extensions`).
2. Bật **Chế độ dành cho nhà phát triển** → **Tải tiện ích đã giải nén** → chọn thư mục `extension`.
3. Mở QT Downloader. Biểu tượng extension báo "đã kết nối" là xong.

Khi QT Downloader không chạy, trình duyệt tự tải như bình thường. Tắt tạm hoặc bỏ qua một trang ngay trong popup
của extension.

Muốn extension mở được app khi app chưa chạy (menu chuột phải **Tải bằng QT Downloader**, nút **Mở QT Downloader** trên
popup): trong app vào **Tuỳ chọn → Trình duyệt → Cho phép trình duyệt mở QT Downloader** (đăng ký giao thức
`qtdownloader://` vào `HKCU\Software\Classes`, bỏ chọn thì gỡ). Trình duyệt sẽ hỏi "Mở QT Downloader?" — chọn Mở. Không
mở được thì link được chuyển cho trình duyệt tải, kèm thông báo lý do. Hoặc bật **Tuỳ chọn → Chung → Khởi động
cùng Windows** để app luôn chạy sẵn dưới khay. Cả hai mặc định tắt.

## Cấu trúc

```
qtdownloader/core/     engine, không phụ thuộc giao diện
  segments.py       thuật toán chia đoạn động
  http_task.py      tải 1 tệp: worker, cửa sổ yêu cầu, retry, checkpoint, checksum
  hls.py            tải luồng HLS
  engine.py         hàng đợi, lịch, giới hạn tốc độ, snapshot cho UI
  api_server.py     API 127.0.0.1 cho extension
  fileio.py         ghi song song vào tệp sparse, Mark-of-the-Web
qtdownloader/ui/       giao diện PySide6
extension/          extension Manifest V3
installer.iss       bộ cài Inno Setup (+ installer/Vietnamese.isl)
tests/              máy chủ thử nghiệm + bộ test pytest
```

Dữ liệu (danh sách tải, cài đặt, log) nằm ở `%LOCALAPPDATA%\QTDownloader`. Đặt biến `QTDOWNLOADER_DATA` để dùng thư mục khác.

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
- Chỉ tải nội dung bạn có quyền tải. QT Downloader không vượt DRM và không dùng mã, icon hay thương hiệu của IDM.
  "Internet Download Manager"/"IDM" là thương hiệu của chủ sở hữu tương ứng; QT Downloader không liên quan tới họ.

## Đóng góp

Mọi người đều có thể đóng góp: báo lỗi, đề xuất tính năng, sửa tài liệu hay gửi mã. Xem
[CONTRIBUTING.md](CONTRIBUTING.md) (cách chạy, test, quy ước) và [Quy tắc ứng xử](CODE_OF_CONDUCT.md). Lỗ hổng bảo
mật xin báo riêng theo [SECURITY.md](SECURITY.md).

## Giấy phép

QT Downloader phát hành theo giấy phép [MIT](LICENSE). Bản đóng gói `.exe` có kèm các thư viện bên thứ ba (Qt/PySide6
theo LGPL-3.0, Python, httpx…) — xem [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

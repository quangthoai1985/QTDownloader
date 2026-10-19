# Lịch sử thay đổi

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/); phiên bản theo [SemVer](https://semver.org/lang/vi/).
Mỗi lần làm việc, Agent thêm mục mới **ở trên cùng** (ngày, việc đã làm, lỗi gặp phải, việc còn dở).

## [Chưa phát hành]

### Việc còn dở / ưu tiên kế tiếp
- Kiểm thử với máy chủ thật trên Internet (chưa làm lần nào).
- Token ghép đôi cho API `127.0.0.1:41888`.
- Xem thêm [CLAUDE.md §7](CLAUDE.md#7-việc-cần-làm-tiếp-theo-thứ-tự-ưu-tiên).

## [1.0.0] — 2026-10-19

Phiên bản đầu tiên, làm trong một phiên với Claude Code.

### Thiết kế
- Viết tài liệu thiết kế engine [docs/THIET_KE.md](docs/THIET_KE.md): vì sao đa kết nối nhanh hơn, chia
  đoạn động, tải tiếp, lớp mạng, tích hợp trình duyệt, HLS.
- Chọn công nghệ Python + PySide6 + httpx vì máy phát triển không có .NET/Rust.

### Thêm — engine (`tdownload/core/`)
- Chia đoạn động: kết nối xong lấy nửa sau đoạn còn lại lớn nhất, tái dùng keep-alive.
- Cửa sổ yêu cầu thích nghi (~4 giây tải, 512 KB–64 MB); cắt đoạn sau cửa sổ đang bay để không huỷ kết nối.
- Ngưỡng chia đoạn động theo tốc độ đo được (tối thiểu 128 KB) để phần cuối tệp không dồn cho 1 kết nối.
- Mở dần kết nối (0,12 s/cái); AIMD theo host khi gặp 429/503/từ chối kết nối/403 ở kết nối phụ; nhớ giới hạn
  theo host, 30 giây sau thử tăng lại.
- Probe bằng `GET Range: bytes=0-0`; đọc `Content-Disposition` (cả `filename*` UTF-8); kiểm `Content-Range` từng
  phản hồi; `If-Range` với ETag mạnh / Last-Modified; tệp trên server đổi → tải lại từ đầu, không trộn dữ liệu.
- Server không hỗ trợ Range / không có `Content-Length` → chế độ 1 kết nối (đứt thì tải lại từ đầu).
- Ghi thẳng vào tệp sparse đã đặt trước kích thước (`.tdpart`), không cần bước ghép phần.
- Checkpoint 3 giây (chụp vị trí → fsync → lưu SQLite); tự tải tiếp khi mở lại app.
- Tải đồng thời từ nhiều mirror (mirror khác kích thước bị loại).
- Giới hạn tốc độ token bucket: toàn cục + riêng từng tệp, đổi được khi đang tải.
- Hàng đợi (số tệp đồng thời, thứ tự), lịch hẹn giờ bắt đầu/dừng theo ngày trong tuần, hành động khi xong.
- Kiểm checksum (`sha256:`/`md5:`…), tự tìm tệp `.sha256` cạnh link.
- Mark-of-the-Web (`Zone.Identifier`) cho tệp tải xong.
- Kiểm dung lượng ổ trước khi tải; cảnh báo server trả `text/html`.
- HLS: chọn biến thể, tải song song segment, ghép `.ts`/`.mp4` (fMP4), remux bằng ffmpeg nếu có; từ chối luồng mã
  hoá và luồng live.
- API cục bộ `127.0.0.1:41888` (`/api/ping`, `/api/add`, `/api/add-batch`) kiểm Host/Origin/CORS.
- CLI `python -m tdownload.cli`.

### Thêm — giao diện (`tdownload/ui/`)
- Cửa sổ chính kiểu IDM: thanh công cụ, cây phân loại (Tệp nén/Tài liệu/Âm nhạc/Chương trình/Video/Khác, Chưa
  xong, Đã xong, Hàng đợi), bảng có thanh tiến trình, ô tìm kiếm, thanh trạng thái (tốc độ, giới hạn nhanh).
- Hộp thoại: Thêm URL (tự kiểm tra máy chủ, chọn chất lượng HLS, nâng cao: referer/cookie/mirror/checksum/giới
  hạn), Tải hàng loạt (mẫu `[001-100]`, lọc theo đuôi), Tuỳ chọn, Lịch hẹn, Thuộc tính + Cập nhật địa chỉ tải,
  Tải xong, Đếm ngược tắt máy.
- Cửa sổ tiến trình: thanh phân đoạn tô màu theo kết nối, bảng kết nối, đồ thị tốc độ, giới hạn tốc độ riêng.
- Khay hệ thống, theo dõi clipboard, kéo-thả link, dán nhiều link, nhập `.txt`/`.ef2` của IDM, xuất danh sách.
- Chỉ chạy 1 phiên bản; mở lần 2 kèm URL thì chuyển sang phiên bản đang chạy.
- Bộ icon SVG tự vẽ, đổi màu theo sáng/tối.

### Thêm — extension (`extension/`, Manifest V3)
- Tự chuyển tải xuống sang TDownload theo đuôi tệp/MIME, kích thước tối thiểu, danh sách trang loại trừ; app không
  chạy thì để trình duyệt tự tải.
- Menu chuột phải: tải link/ảnh/video, tải liên kết đã chọn, tải tất cả liên kết trên trang.
- Dò HLS/DASH/video trên tab, hiện trong popup kèm nút tải; huy hiệu số lượng.
- Trang tuỳ chọn: cổng, đuôi tệp, kích thước tối thiểu, trang loại trừ.

### Thêm — kiểm thử & đóng gói
- `tests/server.py`: máy chủ mô phỏng giới hạn tốc độ/kết nối, rớt kết nối, không Range, không độ dài, Range ngắn,
  tệp thay đổi, chuyển hướng, HLS.
- 24 test pytest (segments, đa kết nối nhanh hơn, resume sau khi tắt engine, rớt 35% kết nối, 503, giới hạn tốc độ,
  mirror, checksum, HLS, hàng đợi, luật Origin của API, Mark-of-the-Web).
- `build.bat` (PyInstaller) → `dist\TDownload\TDownload.exe` ~90 MB; `tools/make_icons.py`.
- Tài liệu: README, [docs/DE_XUAT_TINH_NANG.md](docs/DE_XUAT_TINH_NANG.md), CLAUDE.md.

### Đã kiểm chứng
- Server giới hạn 1 MB/s mỗi kết nối, tệp 20 MB: 1 kết nối 20,0 s → 8 kết nối 4,5 s; SHA-256 khớp.
- Edge 155 (hồ sơ tạm): extension bắt link và huỷ tải của trình duyệt, TDownload tải với UA của Edge, hash khớp;
  dò được HLS; "Tải tất cả liên kết" qua popup gửi đúng 2 link, bỏ `mailto:`.
- Bản `.exe`: API trả lời, Origin lạ bị chặn 403, link qua API tải về đúng thư mục phân loại, có `Zone.Identifier`.

### Sửa trong quá trình phát triển
- Trùng tên `Engine.start()` (khởi động) với tiếp tục tải → đổi thành `Engine.resume()`.
- Cờ `_stop` dùng chung khiến không chuyển được sang 1 kết nối → thuộc tính `halted`.
- Tạm dừng lúc đang probe xoá mất tiến độ đã lưu → cờ `_probed`.
- Đa kết nối chậm ở tệp nhỏ → ngưỡng chia động, mở kết nối nhanh hơn, cửa sổ đầu nhỏ hơn.
- Tải hàng loạt dùng cookie của trang cho mọi link (có thể gửi sang host khác) → cookie theo từng link.
- Console cp1252 làm crash khi in tiếng Việt → ép UTF-8.
- `.bat` UTF-8 + LF làm `cmd.exe` đọc sai → ASCII + CRLF.
- `settings.json` có BOM bị bỏ qua → đọc `utf-8-sig`.
- Nút chuẩn của Qt hiện tiếng Anh, `&` trong tên tab mất → `vi_buttons()`/`ask()`, `&&`.
- Bản build 151 MB → loại numpy/PIL/opengl32sw → ~90 MB.
- Test đọc snapshot trước khi kịp cập nhật → dùng `.get()`.

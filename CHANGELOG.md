# Lịch sử thay đổi

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/); phiên bản theo [SemVer](https://semver.org/lang/vi/).
Mỗi lần làm việc, Agent thêm mục mới **ở trên cùng** (ngày, việc đã làm, lỗi gặp phải, việc còn dở).

## [Chưa phát hành]

### Việc còn dở / ưu tiên kế tiếp
- Kiểm thử với máy chủ thật trên Internet (chưa làm lần nào).
- Token ghép đôi cho API `127.0.0.1:41888`.
- Thêm tệp LICENSE (người dùng chọn loại giấy phép) và thông báo giấy phép thư viện trong gói phát hành.
- Thử giao thức `tdownload://` **đã đăng ký thật** trên Chrome/Edge/Cốc Cốc (cần người dùng bật tuỳ chọn): hộp
  thoại "Mở TDownload?" trông thế nào, có ô "Luôn cho phép" không, chờ 15 giây có đủ không. Lần này chỉ thử trường
  hợp chưa đăng ký (theo yêu cầu không ghi registry thật).

### Thêm
- 2026-10-19: **extension dùng được khi app chưa chạy.**
  - Menu chuột phải "Tải bằng TDownload" (và nút "Tải" video trên popup): app tắt → mở `tdownload://open?minimized=1`
    ở một tab tạm, chờ API lên (10 giây; 15 giây nếu app từng báo đã bật giao thức) rồi gửi link; không được thì
    `chrome.downloads.download` cho trình duyệt tải, kèm huy hiệu "!", tiêu đề nút và thông báo hệ thống nêu lý do.
    Luồng HLS và "tải tất cả liên kết" không có đường lui → chỉ báo lỗi.
  - `/api/ping` trả thêm `protocol`; extension nhớ vào `storage.local` → app báo chưa bật giao thức thì rơi về trình
    duyệt ngay, không chờ.
  - Popup khi app tắt: nút **Mở TDownload** + một dòng hướng dẫn bật tuỳ chọn. Tuỳ chọn extension mới "Tự mở
    TDownload khi app chưa chạy" (mặc định bật). Thêm quyền `notifications`.
  - App: tuỳ chọn **Cho phép trình duyệt mở TDownload** (Tuỳ chọn → Trình duyệt) đăng ký
    `HKCU\Software\Classes\tdownload`, bỏ chọn thì gỡ; **Khởi động cùng Windows (thu nhỏ xuống khay)**
    (Tuỳ chọn → Chung) ghi `HKCU\...\CurrentVersion\Run` với `--minimized`. Cả hai mặc định tắt; khi mở app, tuỳ
    chọn đang bật mà đường dẫn app đã đổi thì ghi lại. Chạy từ mã nguồn: lệnh là `pythonw "<repo>\run_tdownload.py"`
    (đường dẫn tuyệt đối vì trình duyệt chạy lệnh ở thư mục bất kỳ).
  - `ui/app.py` nhận `tdownload://open[?minimized=1]` và `tdownload://add?url=…&referer=…&filename=…` (chỉ nhận
    http/https, luôn hiện hộp thoại xác nhận); chuyển sang phiên bản đang chạy kèm cờ có hiện cửa sổ hay không.
  - Test: `tests/test_integration.py` (phân tích URL, đăng ký/gỡ trên khoá tạm `HKCU\Software\TDownloadTest`) và
    `tests/ext_harness.mjs` (chạy `background.js` thật với API `chrome` giả: 5 kịch bản). 40/40 test qua.

### Sửa
- 2026-10-19: extension có thể lặp vô hạn "gửi app → lỗi → trình duyệt tải → bắt lại → gửi app…" khi app trả lời
  ping nhưng `/api/add` lỗi. Link cố ý giao lại cho trình duyệt giờ được ghi nhớ để `downloads.onCreated` bỏ qua.
  - Đã thử trên Edge 155 hồ sơ tạm, app tắt, giao thức chưa đăng ký: tab tạm `about:blank` đứng suốt thời gian
    chờ (lúc thử là 6 giây, sau đó nâng lên 10; Edge không hiện hộp thoại nào), đóng lại, trình duyệt nhận tải, có thông báo; popup hiện nút "Mở TDownload"; bấm nút
    rồi tự chạy app với `tdownload://open` → extension nhận ra app sau ~6 giây. Thử `tdownload://add?url=…` lần 2 →
    chuyển sang phiên bản đang chạy, hộp thoại hiện đúng tên tệp tiếng Việt. Bấm menu chuột phải thật thì không tự
    động hoá được qua CDP — thân hàm xử lý menu đã chạy qua harness Node.

### Thay đổi
- 2026-10-19: repo chuyển sang **công khai** để tính năng báo bản mới hoạt động; đã kiểm với GitHub thật (không
  đăng nhập đọc được Release `v1.0.0`, SHA-256 của gói khớp).
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

### Thêm — phiên bản & cập nhật
- `tdownload/__init__.py` (`__version__`, `GITHUB_REPO`) là nguồn duy nhất của số phiên bản; test bắt lệch với
  `extension/manifest.json` và CHANGELOG.
- `TDownload.exe` có tài nguyên phiên bản Windows (Properties → Details) sinh từ `__version__`
  (`tools/make_version_file.py`).
- Phát hiện bản mới qua GitHub Releases (`core/updater.py`): tự kiểm tra 1 lần/ngày (chỉ khi có giao diện, sau
  khởi động 20 giây), menu Trợ giúp → Kiểm tra bản mới…, hộp thoại hiện ghi chú phát hành, nút "Có bản x.y.z" trên
  thanh trạng thái, thông báo khay; "Tải bản mới" tải gói `TDownload-x.y.z-win64.zip` bằng chính TDownload và kiểm
  SHA-256 theo `SHA256SUMS.txt` của Release; "Bỏ qua bản này"; tuỳ chọn tắt. Địa chỉ API đổi được bằng biến
  `TDOWNLOAD_UPDATE_URL`.
- `tools/package_release.py` tạo `release/` gồm zip app, zip extension, `SHA256SUMS.txt`.

### Thêm — kiểm thử & đóng gói
- `tests/server.py`: máy chủ mô phỏng giới hạn tốc độ/kết nối, rớt kết nối, không Range, không độ dài, Range ngắn,
  tệp thay đổi, chuyển hướng, HLS.
- 32 test pytest (segments, đa kết nối nhanh hơn, resume sau khi tắt engine, rớt 35% kết nối, 503, giới hạn tốc độ,
  mirror, checksum, HLS, hàng đợi, luật Origin của API, Mark-of-the-Web, đồng bộ phiên bản, kiểm tra cập nhật với
  GitHub Releases giả lập).
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
- Test "server giới hạn 2 kết nối" dùng tệp 4 MB nên engine không bao giờ mở kết nối thứ 3 (ngưỡng chia 1 MB) →
  test chỉ qua nhờ may về thời gian; đổi sang tệp 12 MB.
- Chế độ "chỉ 1 phiên bản" dùng chung tên cho mọi thư mục dữ liệu → bản chạy thử với `TDOWNLOAD_DATA` đánh thức
  app đang dùng; nay tên gắn với thư mục dữ liệu.

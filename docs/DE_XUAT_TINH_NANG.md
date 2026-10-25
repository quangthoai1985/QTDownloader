# Đề xuất tính năng cho QT Downloader

Chia 2 phần: **(A)** những điểm QT Downloader đã làm *tốt hơn / khác* IDM trong bản này, và **(B)** đề xuất tiếp theo,
xếp theo giá trị cho người dùng (đặc biệt người dùng Việt Nam) so với công sức.

Ký hiệu công sức: 🟢 nhỏ (≤ 3 ngày) · 🟡 vừa (1–2 tuần) · 🔴 lớn (≥ 1 tháng).

---

## A. Đã có trong bản này (vượt hoặc khác IDM)

| # | Tính năng | Vì sao hay | Ở đâu trong mã |
|---|---|---|---|
| 1 | **Tải đồng thời từ nhiều nguồn (mirror)** | Không chỉ dùng link thay thế khi link chính lỗi: QT Downloader chia các kết nối cho *tất cả* mirror cùng lúc → cộng dồn băng thông của nhiều máy chủ. Mirror khác kích thước bị loại để không trộn dữ liệu | `http_task._probe_mirrors`, ô "Nguồn phụ" |
| 2 | **Cửa sổ yêu cầu + ngưỡng chia động** | Mỗi kết nối gửi Range theo "cửa sổ" ~4 giây tải; khi chia đoạn thì cắt sau cửa sổ đang bay → kết nối cũ đọc trọn phản hồi, giữ được keep-alive. Ngưỡng chia đoạn tự co theo tốc độ đo được → phần cuối tệp không bị dồn cho 1 kết nối chậm | `segments.split_largest`, `http_task._split_threshold` |
| 3 | **Lịch sự với máy chủ (AIMD)** | Gặp 429/503/từ chối kết nối thì tự giảm số kết nối, nhớ giới hạn theo host, sau 30 giây yên ổn mới tăng lại — tránh bị chặn IP | `http_task._reduce_cap` |
| 4 | **Ghi thẳng vào tệp sparse** | Không có bước "ghép các phần" khi xong (tệp nhiều GB không phải chờ), không khựng do Windows điền số 0 | `fileio.PartFile` |
| 5 | **Resume an toàn tuyệt đối** | Checkpoint chỉ ghi nhận vị trí *sau* `fsync`; `If-Range` với ETag mạnh; kiểm `Content-Range` từng phản hồi; tệp trên máy chủ đổi thì tải lại thay vì trộn dữ liệu cũ/mới | `http_task._checkpoint`, `_fetch` |
| 6 | **Tự kiểm tra toàn vẹn** | Tự tìm `<tệp>.sha256` cạnh link (GitHub release, ảnh ISO…) để kiểm tra sau khi tải; hoặc nhập `sha256:` / `md5:` | `http_task._find_sidecar_checksum` |
| 7 | **Mark-of-the-Web** | Gắn `Zone.Identifier` như trình duyệt → SmartScreen / Office Protected View vẫn cảnh báo tệp từ Internet | `fileio.mark_of_the_web` |
| 8 | **Cookie đúng host** | Cookie lấy theo từng link và gắn vào đúng host gốc → không rò cookie sang CDN/host khác khi chuyển hướng hoặc khi tải hàng loạt | `engine.make_client`, `extension/background.js` |
| 9 | **Cảnh báo "trang web thay vì tệp"** | Phát hiện máy chủ trả `text/html` (trang đăng nhập/link hết hạn) trước khi tải | `AddUrlDialog._on_probe` |
| 10 | **Kiểm tra dung lượng ổ trước khi tải** | Báo ngay nếu ổ không đủ chỗ, không tải nửa chừng | `http_task._prepare_file` |
| 11 | **Nhập danh sách `.ef2` của IDM** | Chuyển hàng loạt link từ IDM sang trong 1 bước | `main_window.parse_ef2` |
| 12 | **Không cần ghi registry để tích hợp trình duyệt** | Extension gọi API `127.0.0.1` có kiểm Host/Origin/CORS; IDM cần native messaging host + registry. Muốn extension mở được app khi app tắt thì người dùng tự bật giao thức `qtdownloader://` (HKCU, gỡ được); không mở được thì link rơi về trình duyệt, không mất | `core/api_server.py`, `core/integration.py` |
| 13 | **Từ chối DRM rõ ràng** | Luồng HLS có `#EXT-X-KEY` bị từ chối kèm thông báo, không âm thầm tải rác | `core/hls.py` |
| 14 | **CLI headless** | `python -m qtdownloader.cli URL -c 16` — dùng trong script, máy chủ, CI | `qtdownloader/cli.py` |

---

## B. Đề xuất tiếp theo

### B1. Tốc độ & mạng

| Đề xuất | Lợi ích | Công sức | Gợi ý cách làm |
|---|---|---|---|
| **Gộp băng thông nhiều mạng** (Wi-Fi + 4G chia sẻ/USB, 2 đường cáp) | Tải nhanh gấp đôi khi có 2 đường; cứu cánh lúc mạng cáp quang chậm giờ cao điểm | 🟡 | Mỗi worker bind socket vào 1 interface (`local_address` của httpx transport); phân việc theo tốc độ từng đường — thuật toán chia đoạn hiện tại dùng lại được nguyên |
| **Chế độ nhường mạng** | Tự giảm tốc khi bạn họp Zoom/Meet, chơi game; tải hết tốc lực khi máy rảnh | 🟡 | Đo RTT tới gateway mỗi giây (kiểu LEDBAT): độ trễ tăng > 50 ms → hạ `global_speed_limit`; hoặc phát hiện ứng dụng toàn màn hình |
| **Hồ sơ tốc độ theo giờ** | 8h–17h giới hạn 2 MB/s, đêm không giới hạn | 🟢 | Mở rộng `Schedule` thành danh sách khung giờ → gọi `limiter.set_rate` trong `_check_schedule` |
| **Nhận biết mạng tính phí (metered)** | Tự dừng khi chuyển sang 4G/hotspot, chạy lại khi về Wi-Fi | 🟢 | `Windows.Networking.Connectivity` → `NetworkCostType` (qua `winrt` hoặc PowerShell) |
| **HTTP/3 (QUIC)** | Ổn định hơn trên mạng di động mất gói | 🔴 | `aioquic`; chỉ bật với host quảng bá `Alt-Svc: h3` |
| **Quota dữ liệu tháng** | Không vượt gói cước | 🟢 | Đếm byte theo tháng trong SQLite; cảnh báo/dừng khi chạm ngưỡng |

### B2. Độ tin cậy

| Đề xuất | Lợi ích | Công sức | Gợi ý cách làm |
|---|---|---|---|
| **Tự làm mới link hết hạn** | Link Google Drive/Fshare/CDN có chữ ký hết hạn sau vài giờ → hiện phải dán link mới bằng tay | 🟡 | Khi gặp 403 lúc tải tiếp: extension theo dõi lần sau người dùng mở lại trang đó, bắt link mới cùng tên + cùng kích thước → gọi `engine.refresh_url` tự động |
| **Xác thực theo `Repr-Digest` / `Content-MD5`** | Kiểm toàn vẹn ngay cả khi không có tệp `.sha256` | 🟢 | Đọc header RFC 9530 khi probe, lưu vào `checksum` |
| **Phát hiện trùng lặp** | Không tải lại tệp đã có (cùng URL, hoặc cùng tên + kích thước + ETag) | 🟢 | Tra lịch sử trong SQLite trước `engine.add`; hỏi "Mở tệp đã có / Tải lại" |
| **Tải tuần tự để xem trước video** | Xem phim ngay khi đang tải (mở bằng VLC) | 🟡 | Thêm chế độ chia đoạn "ưu tiên đầu tệp": worker mới lấy đoạn chưa xong gần đầu nhất thay vì đoạn lớn nhất |
| **Sửa tệp hỏng** | Tệp đã tải nhưng sai checksum → chỉ tải lại vùng hỏng | 🔴 | Cần hash theo khối (Metalink 4 / server cung cấp), so từng khối rồi tải lại khối sai |

### B3. Sau khi tải

| Đề xuất | Lợi ích | Công sức | Gợi ý cách làm |
|---|---|---|---|
| **Quét virus bằng Windows Defender** | An toàn hơn với tệp `.exe/.zip` (IDM có tuỳ chọn gọi antivirus) | 🟢 | `MpCmdRun.exe -Scan -ScanType 3 -File <tệp> -DisableRemediation`; báo kết quả trong hộp thoại Tải xong |
| **Tự giải nén** | Tải xong `.zip/.7z/.rar` (kể cả `part1.rar`) là có thư mục dùng ngay | 🟢 | `zipfile` có sẵn; 7z/rar qua `7z.exe` nếu có |
| **Quy tắc tự động** | "Link từ `*.edu.vn` → thư mục Học tập, 4 kết nối"; "> 2 GB → vào hàng đợi đêm" | 🟡 | Bảng rule (điều kiện: domain/đuôi/kích thước/trang nguồn → hành động) áp dụng trong `engine.add` |
| **Thông báo qua Telegram/Zalo/Discord** | Biết tệp lớn tải xong khi không ngồi ở máy | 🟢 | Webhook khi có sự kiện `completed`/`error` |
| **Đẩy lên đám mây / NAS** | Tải xong tự chép lên Google Drive, OneDrive, NAS | 🟡 | Hậu xử lý cấu hình được (lệnh hoặc rclone) |
| **Đổi tên theo mẫu** | `{ngày}_{tên miền}_{tên}` cho dễ quản lý | 🟢 | Template trong Tuỳ chọn, áp lúc tạo `filename` |

### B4. Video

| Đề xuất | Lợi ích | Công sức | Gợi ý cách làm |
|---|---|---|---|
| **DASH (.mpd) + ghép tiếng/hình** | Nhiều trang dùng DASH tách riêng video và audio | 🟡 | Parser MPD (SegmentTemplate/SegmentBase), tải 2 luồng song song, `ffmpeg -c copy` ghép |
| **Tích hợp yt-dlp (tuỳ chọn)** | Hỗ trợ hàng nghìn trang video | 🟢 | Gọi `yt-dlp -J` lấy định dạng → engine tải đa kết nối. Nhắc người dùng tôn trọng điều khoản của trang |
| **Tải phụ đề, tách MP3** | Tiện cho học tập | 🟢 | Đọc `#EXT-X-MEDIA:TYPE=SUBTITLES`; `ffmpeg -vn` |

### B5. Trải nghiệm

| Đề xuất | Lợi ích | Công sức | Gợi ý cách làm |
|---|---|---|---|
| **Điều khiển từ điện thoại** | Thấy link trên điện thoại → gửi về máy tính tải; xem tiến độ từ xa | 🟡 | Web UI nhẹ trên LAN (đã có API) + ghép đôi bằng mã QR + token |
| **Ô thả nổi (drop target)** | Kéo link vào ô nhỏ luôn nổi trên màn hình như IDM | 🟢 | Cửa sổ không viền, luôn trên cùng, nhận kéo-thả |
| **Thống kê** | Tổng dung lượng, tốc độ trung bình theo host, tỉ lệ thành công | 🟢 | Truy vấn SQLite + biểu đồ |
| **Bản portable** | Chạy từ USB, dữ liệu cạnh exe | 🟢 | Đặt `QTDOWNLOADER_DATA` = thư mục cạnh exe khi có tệp `portable.txt` |
| **Firefox** | Thêm người dùng Firefox | 🟢 | Manifest MV3 dạng `background.scripts` + `browser_specific_settings` |
| **Menu chuột phải trong Explorer** | "Tải lại link này", "Kiểm tra checksum" | 🟡 | Shell extension / Windows 11 sparse package |

### B6. Bảo mật & doanh nghiệp

| Đề xuất | Lợi ích | Công sức | Gợi ý cách làm |
|---|---|---|---|
| **Ghép đôi extension bằng token** | Hiện mọi tiến trình *trên máy* đều gọi được API localhost; token ngăn phần mềm lạ âm thầm thêm tải | 🟢 | App sinh token, extension nhận một lần qua trang ghép đôi; API yêu cầu header `X-QTDownloader-Token` |
| **Ký số Authenticode** | Không bị SmartScreen chặn bản cài | 🟡 (chi phí chứng thư) | Ký `QTDownloader.exe` + bộ cài Inno Setup |
| **Proxy PAC, NTLM/Kerberos** | Dùng được trong mạng công ty | 🟡 | `pypac` cho PAC; SSPI qua `pyspnego` |
| **Mã hoá cookie lưu trữ** | Cookie phiên trong DB không bị đọc lén | 🟢 | DPAPI (`CryptProtectData`) cho cột cookie |

---

## Lộ trình gợi ý

1. **Ngay (1–2 tuần):** ghép đôi token, quét Defender, tự giải nén, hồ sơ tốc độ theo giờ, phát hiện trùng lặp, bản portable.
2. **Tiếp theo (1 tháng):** tự làm mới link hết hạn, chế độ nhường mạng, quy tắc tự động, DASH, điều khiển từ điện thoại.
3. **Dài hạn:** gộp băng thông nhiều mạng, HTTP/3, sửa tệp hỏng theo khối, Firefox/shell extension, bộ cài có ký số.

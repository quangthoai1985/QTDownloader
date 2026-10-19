# Thiết kế engine tải của TDownload

Tài liệu này giải thích vì sao tải nhiều kết nối nhanh hơn và cách TDownload cài đặt từng cơ chế. Tham chiếu:
RFC 9110 (HTTP Semantics — Range, `206 Partial Content`, `If-Range`), RFC 8216 (HTTP Live Streaming).

---

## 1. Vì sao tải nhiều kết nối lại nhanh hơn?

Một kết nối TCP đơn lẻ hiếm khi dùng hết băng thông:

| Nguyên nhân | Giải thích | Tác dụng của đa kết nối |
|---|---|---|
| Cửa sổ TCP / độ trễ (BDP) | Thông lượng ≤ `cửa_sổ / RTT`. Server ở xa (RTT 200 ms) + cửa sổ nhỏ ⇒ chậm | N kết nối ≈ N cửa sổ song song |
| Mất gói | Công thức Mathis: `tốc độ ≈ MSS / (RTT·√p)` — mạng Wi-Fi/4G mất gói làm 1 luồng tụt mạnh | Mất gói chỉ làm chậm 1 luồng, các luồng khác bù |
| Server giới hạn theo kết nối | Nhiều CDN/hosting giới hạn mỗi kết nối (vd 500 KB/s) | Tổng = N × giới hạn |
| Slow-start | Mỗi kết nối mới phải "khởi động"; luồng đơn tăng tốc chậm | Khởi động song song, đạt đỉnh sớm hơn |

Điều kiện cần: server hỗ trợ **HTTP Range** (`Accept-Ranges: bytes`, trả `206 Partial Content`). Nếu server bỏ qua
Range (trả `200`), chỉ tải được 1 luồng và không tải tiếp được. Đa kết nối cũng vô ích nếu server giới hạn theo IP.

## 2. Chia đoạn động — `core/segments.py`, `core/http_task.py`

Chia tĩnh (cắt tệp thành N phần bằng nhau ngay từ đầu) để lại "đuôi" cho kết nối chậm nhất. TDownload chia **trong lúc
tải**:

1. Probe bằng `GET Range: bytes=0-0` để biết kích thước, ETag, Last-Modified, khả năng Range.
2. Mở dần kết nối (0,12 giây/kết nối). Mỗi kết nối mới **lấy nửa sau của đoạn còn lại lớn nhất**.
3. Kết nối tải xong phần của mình **không đóng** mà lấy tiếp nửa sau của đoạn lớn nhất đang dở → tái dùng
   keep-alive, không tốn bước bắt tay TCP/TLS.
4. Mỗi kết nối gửi Range theo một **cửa sổ yêu cầu** ≈ 4 giây tải (512 KB–64 MB). Khi chia đoạn, điểm cắt được đặt
   **sau cửa sổ đang bay** → kết nối cũ đọc trọn phản hồi, không phải huỷ giữa chừng.
5. Ngưỡng ngừng chia tự co theo tốc độ đo được (≈ 1,5 giây × tốc độ trung vị, tối thiểu 128 KB) để phần cuối tệp
   không dồn cho 1 kết nối.

```
t0: [=========================== đoạn 1 ===========================]
t1: [====== đoạn 1 ======>.......][====== đoạn 2 (nửa sau) =======>]
t2: [== 1 ==>....][=== 3 ===>....][=== 2 ===>.....][=== 4 ===>.....]
    đoạn 1 xong → kết nối 1 lấy nửa sau của đoạn đang còn nhiều nhất …
```

`Segment.pos` = byte đã nhận (kể cả trong bộ đệm), `Segment.written` = byte đã ghi xuống đĩa; trạng thái lưu theo
`written`.

## 3. Lịch sự với máy chủ (AIMD)

Gặp `429`/`503`/từ chối kết nối/`403` ở kết nối phụ → giảm trần số kết nối của tệp và nhớ theo host; sau 30 giây yên
ổn thì thử tăng lại. Tránh bị máy chủ chặn IP vì mở quá nhiều kết nối.

## 4. Tải tiếp an toàn

- Checkpoint mỗi 3 giây theo thứ tự **chụp vị trí → fsync → lưu SQLite**: không bao giờ ghi nhận byte chưa nằm trên
  đĩa.
- Mở lại: so ETag (mạnh) / Last-Modified / kích thước với lần trước; gửi `If-Range`; kiểm `Content-Range` của **mọi**
  phản hồi. Tệp trên máy chủ đã đổi → tải lại từ đầu thay vì trộn dữ liệu cũ/mới.
- Link hết hạn (link có chữ ký thời gian): **Cập nhật địa chỉ tải** — dán link mới, kiểm cùng kích thước rồi tải tiếp.
- Server không hỗ trợ Range hoặc không có `Content-Length` → chế độ 1 kết nối, đứt thì tải lại từ đầu.

## 5. Ghi tệp — `core/fileio.py`

Ghi thẳng vào **một tệp sparse** đặt trước kích thước (`<tên>.tdpart`, `FSCTL_SET_SPARSE` + `truncate`), mỗi kết nối
ghi đúng offset của mình. Không có bước "ghép các phần" khi xong; NTFS không phải điền số 0 khi ghi ở offset xa. Xong
thì `os.replace` sang tên thật và gắn Mark-of-the-Web (`Zone.Identifier`).

## 6. Lớp mạng

- `httpx`, mặc định **HTTP/1.1** — mỗi "kết nối" là một kết nối TCP thật. HTTP/2 là tuỳ chọn (gộp mọi luồng vào 1 TCP
  nên thường không tăng tốc).
- Giữ `Cookie` (đặt vào jar theo đúng host), `Referer`, `User-Agent` của trình duyệt để tải được tệp cần đăng nhập;
  cookie không đi theo chuyển hướng sang host khác.
- Giới hạn tốc độ token bucket: toàn cục + riêng từng tệp, đổi được khi đang tải.

## 7. Tích hợp trình duyệt

| Thành phần | Cách làm |
|---|---|
| Extension MV3 (Chrome/Edge/Cốc Cốc) | `downloads.onCreated` → ping app → huỷ tải của trình duyệt → gửi URL + cookie (theo từng link) + referer + UA |
| Cầu nối extension ↔ app | **HTTP `127.0.0.1:41888`** — không cần ghi registry. Kiểm Host (chống DNS rebinding), Origin chỉ nhận trang extension, POST bắt buộc `application/json` (ép preflight CORS) |
| Phát hiện video | `webRequest.onHeadersReceived` dò `.m3u8`/video theo tab |

Ngoài ra: theo dõi clipboard, kéo-thả link, nhập danh sách `.txt`/`.ef2`.

## 8. HLS — `core/hls.py`

Master playlist → chọn biến thể; tải segment song song vào `<tệp>.tdhls/`; ghép `.ts` (có ffmpeg thì remux sang
`.mp4`); fMP4 (`#EXT-X-MAP`) → `.mp4`. Luồng có `#EXT-X-KEY` (AES-128, SAMPLE-AES…) bị **từ chối** kèm thông báo —
TDownload không vượt DRM. Luồng live chưa hỗ trợ.

## 9. Giới hạn cố hữu

- Chỉ bắt được link từ trình duyệt (qua extension), clipboard, kéo-thả; không bắt link từ ứng dụng khác (cần driver
  mạng ký số — không làm).
- Extension chỉ thấy tải xuống sau khi trình duyệt đã bắt đầu; tải từ form POST và `blob:` không chuyển được.

# Chính sách bảo mật

## Phiên bản được hỗ trợ

Chỉ bản phát hành mới nhất trên [GitHub Releases](../../releases/latest) nhận bản vá bảo mật.

## Báo lỗ hổng

**Đừng mở issue công khai.** Hãy báo riêng qua GitHub: tab **Security → Report a vulnerability** của repo. Nếu nút
này chưa có, mở một issue chỉ ghi "Cần kênh báo lỗ hổng riêng" (không kèm chi tiết) để người duy trì liên hệ lại.

Xin mô tả: phiên bản, các bước tái hiện, ảnh hưởng. Người duy trì sẽ phản hồi sớm nhất có thể, thống nhất thời điểm
công bố sau khi có bản vá, và ghi công người báo nếu bạn muốn.

## Những phần nhạy cảm

- API cục bộ `127.0.0.1:41888` (`core/api_server.py`): kiểm Host/Origin/CORS — mọi cách khiến trang web lạ thêm link
  hay đọc dữ liệu đều là lỗ hổng.
- Extension trình duyệt: cookie chỉ được gửi cho đúng host của link.
- Giao thức `tdownload://` và khởi động cùng Windows (`core/integration.py`): chỉ ghi registry khi người dùng bật.
- Tên tệp từ máy chủ (`Content-Disposition`): không được thoát khỏi thư mục tải (path traversal).
- Cơ chế cập nhật (`core/updater.py`): kiểm SHA-256 của gói tải về.

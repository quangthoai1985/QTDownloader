"""QT Downloader — trình quản lý tải xuống đa kết nối (lấy cảm hứng từ cơ chế của IDM)."""

__version__ = "1.1.0"
APP_NAME = "QT Downloader"              # tên hiển thị
APP_ID = "QTDownloader"                 # tên kỹ thuật: tệp .exe, thư mục dữ liệu, khoá registry
GITHUB_REPO = "quangthoai1985/QTDownloader"   # nơi app tìm bản phát hành mới (GitHub Releases)
# Bộ cài nhận ra app đang mở qua mutex này (installer.iss: AppMutex) — phải trùng nhau
APP_MUTEX_NAME = "QTDownloader.AppMutex"
# AppId của bộ cài Inno Setup (installer.iss) — KHÔNG BAO GIỜ đổi: cài đè và gỡ cài đặt dựa vào nó
INNO_APP_ID = "{60877C1B-878F-46D0-A5B2-F015CCF3F562}"

// Tab tạm do background.js mở khi app chưa chạy. Điều hướng tới tdownload:// TỪ trang của extension (có origin
// khởi tạo) thì hộp thoại của trình duyệt có ô "Luôn cho phép"; mở thẳng bằng tabs.create thì không có.
const target = new URLSearchParams(location.search).get("u") || "";
if (/^tdownload:\/\/open(\?minimized=1)?$/.test(target)) location.href = target;

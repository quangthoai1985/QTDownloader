# Ký số qua SignPath Foundation (miễn phí cho dự án nguồn mở)

Chính sách công khai: [docs/CODE_SIGNING.md](../docs/CODE_SIGNING.md). Workflow: [.github/workflows/release.yml](../.github/workflows/release.yml).

## 1. Đăng ký (một lần)
1. Bật xác thực 2 lớp (MFA) cho tài khoản GitHub.
2. Nộp đơn tại <https://signpath.org/apply> cho repo `quangthoai1985/QTDownloader` (MIT, phát hành trên GitHub
   Releases, build bằng GitHub Actions). Chờ SignPath Foundation duyệt và gửi thông tin tổ chức SignPath.
3. Đăng nhập <https://app.signpath.io>, bật MFA cho tài khoản SignPath.

## 2. Cấu hình trên SignPath (sau khi được duyệt)
1. **Trusted Build System**: liên kết *GitHub.com* với project (làm theo hướng dẫn của SignPath, cài GitHub App nếu
   được yêu cầu) — bắt buộc cho chương trình nguồn mở (origin verification).
2. **Project** (ghi lại *project slug*, ví dụ `QTDownloader`), thêm 2 **artifact configuration**:
   - slug `app` ← nội dung [`artifact-configuration-app.xml`](artifact-configuration-app.xml)
   - slug `installer` ← nội dung [`artifact-configuration-installer.xml`](artifact-configuration-installer.xml)
3. **Signing policy** dùng chứng thư của SignPath Foundation, bật **duyệt thủ công** (approver: quangthoai1985);
   ghi lại *signing policy slug* (ví dụ `release-signing`).
4. Tạo **CI user** có quyền *submitter* trên policy đó → lấy **API token**.

## 3. Cấu hình repo GitHub
Settings → Secrets and variables → Actions:
- **Secret** `SIGNPATH_API_TOKEN` = API token của CI user.
- **Variables**: `SIGNPATH_ORGANIZATION_ID` (Organization ID trên SignPath), `SIGNPATH_PROJECT_SLUG`,
  `SIGNPATH_SIGNING_POLICY_SLUG`.

Có `SIGNPATH_ORGANIZATION_ID` là workflow tự bật các bước ký. Chưa có thì workflow vẫn phát hành bản chưa ký như cũ.

## 4. Mỗi lần phát hành
Actions → **Phát hành** → Run workflow (tag `vX.Y.Z`). Workflow dừng 2 lần chờ duyệt trên SignPath
(ký `QTDownloader.exe`, rồi ký bộ cài) — vào app.signpath.io bấm **Approve**, mỗi lần chờ tối đa 1 giờ.
Muốn thử trước mà không xuất bản: bỏ chọn **publish**, kết quả ở mục Artifacts của lần chạy.

Đổi tên tệp/ProductName thì sửa cả hai tệp XML ở đây và tải lại lên SignPath (`tests/test_installer.py` đối chiếu).

# Chính sách ký số mã nguồn / Code signing policy

> Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by
> [SignPath Foundation](https://signpath.org/).
>
> Trạng thái / Status: đang chờ SignPath Foundation duyệt — các bản ≤ 1.1.0 chưa được ký
> (application pending; releases up to 1.1.0 are unsigned).

*(English version below.)*

## Tiếng Việt

QT Downloader là phần mềm nguồn mở giấy phép [MIT](../LICENSE). Bản phát hành cho Windows được ký số Authenticode qua
chương trình miễn phí cho dự án nguồn mở của SignPath Foundation, để Windows (SmartScreen, Smart App Control) xác
minh được tệp do dự án này phát hành và chưa bị sửa đổi.

**Tệp được ký**
- `QTDownloader.exe` — chương trình chính (bootloader PyInstaller chứa mã Python của dự án).
- `QTDownloader-<phiên bản>-setup.exe` — bộ cài Inno Setup.

Thư viện bên thứ ba đóng kèm (Qt/PySide6, Python, httpx…) **không** được ký bằng chứng thư này; danh sách và giấy phép
của chúng ở [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

**Quy trình**
- Chỉ ký tệp build tự động bằng GitHub Actions ([`.github/workflows/release.yml`](../.github/workflows/release.yml))
  từ mã nguồn công khai trong repo này, trên máy Windows của GitHub. Không ký tệp build trên máy cá nhân.
- Cấu hình những tệp được ký: [`.signpath/`](../.signpath/).
- Mỗi lần ký phải có người duyệt thủ công trên SignPath. Workflow kiểm chữ ký, cài thử và gỡ thử bộ cài trước khi tạo
  bản phát hành; `SHA256SUMS.txt` được tính **sau** khi ký.

**Vai trò**

| Vai trò | Người |
|---|---|
| Người đóng góp mã (committer) và người duyệt mã (reviewer) | [quangthoai1985](https://github.com/quangthoai1985) |
| Người duyệt yêu cầu ký (approver) | [quangthoai1985](https://github.com/quangthoai1985) |

Mọi thay đổi từ người ngoài được đưa vào qua pull request và phải được người duyệt mã chấp nhận. Tài khoản GitHub và
SignPath của các vai trò trên bật xác thực nhiều lớp (MFA).

**Quyền riêng tư** — xem [chính sách quyền riêng tư](#quyền-riêng-tư--privacy-policy) bên dưới.

**Kiểm tra chữ ký** (PowerShell):

```powershell
Get-AuthenticodeSignature .\QTDownloader-<phiên bản>-setup.exe | Format-List Status, SignerCertificate
Get-FileHash .\QTDownloader-<phiên bản>-setup.exe -Algorithm SHA256   # so với SHA256SUMS.txt của bản phát hành
```

Bản phát hành trước khi có chữ ký (≤ 1.1.0) không được ký; Windows 11 bật Smart App Control sẽ chặn chúng.

## English

QT Downloader is open-source software under the [MIT license](../LICENSE). Windows release binaries are
Authenticode-signed through the SignPath Foundation open-source program.

**Signed files:** `QTDownloader.exe` (the project's PyInstaller bootloader with the project's Python code) and the
Inno Setup installer `QTDownloader-<version>-setup.exe`. Bundled third-party libraries (Qt/PySide6, Python, httpx…) are
**not** signed with this certificate; see [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

**Process:** only binaries built automatically by GitHub Actions ([`.github/workflows/release.yml`](../.github/workflows/release.yml))
from the public source in this repository are signed — never binaries built on a personal machine. The artifact
configurations are in [`.signpath/`](../.signpath/). Every signing request requires manual approval. The workflow
verifies signatures and performs a silent install/uninstall test before publishing; `SHA256SUMS.txt` is computed
after signing.

**Team roles:** committer, reviewer and approver: [quangthoai1985](https://github.com/quangthoai1985). External
contributions are accepted only through reviewed pull requests. Multi-factor authentication is enabled for GitHub and
SignPath accounts of all team members.

## Quyền riêng tư / Privacy policy

**Tiếng Việt.** QT Downloader không thu thập, không gửi dữ liệu cá nhân hay số liệu sử dụng cho tác giả hay bên thứ ba.
Ứng dụng chỉ kết nối mạng khi:
- tải các tệp **bạn** yêu cầu (gửi tới máy chủ của link đó cookie/Referer do bạn hoặc extension trình duyệt cung cấp);
- kiểm tra bản mới: `api.github.com` (bản phát hành của repo này) và tải bộ cài/gói từ GitHub — tắt được trong
  **Tuỳ chọn → Chung**.

API cục bộ cho extension chỉ nghe ở `127.0.0.1`. Danh sách tải, thiết lập và nhật ký chỉ lưu trên máy bạn
(`%LOCALAPPDATA%\QTDownloader`); trình gỡ cài đặt hỏi có xoá chúng không. Không có thông tin nào được gửi cho SignPath
khi bạn dùng ứng dụng — SignPath chỉ nhận tệp build để ký trong lúc phát hành.

**English.** This program will not transfer any information to other networked systems unless specifically requested
by the user or the person installing or operating it. It connects only to (1) the servers of the downloads you start,
and (2) `api.github.com` / GitHub release downloads to check for and download updates — which can be turned off in
*Options → General*. The local API for the browser extension listens on `127.0.0.1` only. No telemetry is collected.

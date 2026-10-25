# CLAUDE.md — Bàn giao dự án QT Downloader cho Agent

> Đọc tệp này trước khi làm bất cứ việc gì. Lịch sử chi tiết: [CHANGELOG.md](CHANGELOG.md).
> Người dùng viết tiếng Việt → trả lời tiếng Việt; chuỗi giao diện và tài liệu viết tiếng Việt có dấu.

## 1. Dự án là gì

**QT Downloader** là trình quản lý & tăng tốc tải xuống cho Windows theo kiểu Internet Download Manager (IDM): chia đoạn
động đa kết nối, tải tiếp sau khi mất mạng/tắt máy, hàng đợi, lịch hẹn, giới hạn tốc độ, tải HLS, bắt link từ trình
duyệt qua extension. Viết bằng **Python 3.14 + PySide6 + httpx**. **Mã nguồn mở, giấy phép MIT**; nhận đóng góp từ
mọi người ([CONTRIBUTING.md](CONTRIBUTING.md)). Thiết kế engine: [docs/THIET_KE.md](docs/THIET_KE.md).

Trạng thái: **v1.1.0 đã phát hành** (2026-10-25, build bằng GitHub Actions) — đổi tên **TDownload → QT Downloader**
(repo `quangthoai1985/QTDownloader`, trước là `TDownload`), **bộ cài Inno Setup** (gỡ được trong Cài đặt › Ứng dụng),
**tự cập nhật như QT PDF Pro**. Bản 1.1.0 **chưa ký số** → Windows 11 bật Smart App Control chặn hẳn bộ cài; đang
chuẩn bị ký số miễn phí qua **SignPath Foundation** (`.signpath/README.md`, `docs/CODE_SIGNING.md`) — chờ người dùng
nộp đơn và cấu hình. Repo GitHub đã được tạo lại ngày 2026-10-19 với lịch sử sạch (đừng tham chiếu mã commit cũ).
68 test qua (5 bỏ qua ngoài Windows), extension đã thử trên Edge 155 thật
(cả giao thức đăng ký thật), bản PyInstaller `QTDownloader.exe` (~86 MB) đã thử tải end-to-end. **Chưa thử với máy chủ thật trên Internet**
(Google Drive, Fshare, Mediafire, CDN lớn) — đây là việc ưu tiên số 1.

## 2. Quy tắc bắt buộc

1. **Chỉ cài đặt từ chuẩn công khai (RFC) và hành vi quan sát được từ bên ngoài.** Không dịch ngược phần mềm khác,
   không sao chép mã/pseudocode, chuỗi, icon, âm thanh của bên thứ ba; không dùng tên "IDM" cho sản phẩm; không
   làm/không mô tả bất kỳ bước bẻ khoá license nào. Không nhận đóng góp có nguồn gốc như vậy.
2. **Giấy phép MIT**: mã mới phải tương thích MIT. Thêm thư viện vào gói `.exe` thì cập nhật `THIRD_PARTY_NOTICES.md`
   và `licenses/` (test `tests/test_release_files.py` kiểm các tệp này có mặt).
3. **Không vượt DRM**: HLS có `#EXT-X-KEY` (AES-128/SAMPLE-AES…) phải bị từ chối kèm thông báo.
4. Không đưa mã engine vào UI; UI chỉ gọi engine qua `engine.call(...)` và đọc `engine.snapshot`.
5. Tệp `.bat` phải **ASCII + CRLF** (xem §6). In tiếng Việt ra console phải `reconfigure(encoding="utf-8")`.

## 3. Chạy, test, build

```bash
python -m pip install -r requirements.txt
python -m qtdownloader                 # GUI (hoặc run.bat); --minimized để khởi động xuống khay
python -m qtdownloader.cli URL -c 16   # headless
python -m pytest -q tests           # ~70 giây, 68 test (có chạy node tests/ext_harness.mjs nếu có Node)
python tests/server.py --port 8765  # máy chủ thử nghiệm để bấm thử trên GUI
build.bat [thư_mục]                 # → <thư_mục mặc định dist>\QTDownloader\QTDownloader.exe
python tools/package_release.py [--dist thư_mục] [--no-installer]   # → release\*-setup.exe, *.zip, SHA256SUMS.txt
                                    # bộ cài cần Inno Setup 6: winget install --id JRSoftware.InnoSetup -e --scope user
```

### Quy trình phát hành phiên bản mới
1. Tăng `__version__` trong `qtdownloader/__init__.py` **và** `"version"` trong `extension/manifest.json`; thêm mục
   `## [x.y.z] — ngày` vào CHANGELOG (test `tests/test_version.py` chặn nếu lệch).
2. `python -m pytest -q tests` → `build.bat` → chạy thử exe với `QTDOWNLOADER_DATA` tạm → `python tools/package_release.py`
   → cài thử bộ cài vào thư mục tạm (`/VERYSILENT /DIR="…"`) rồi gỡ (`unins000.exe /VERYSILENT`). Máy đã có bản cài
   thật (khoá `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{60877C1B-…}_is1`) thì **không** cài thử
   (cùng AppId → gỡ bản thử xoá luôn bản thật) — thử trên máy ảo.
3. Commit, `git tag -a vX.Y.Z`, push tag (hoặc Actions → Phát hành → Run workflow, bỏ chọn `publish` để chạy thử) → workflow `.github/workflows/release.yml` (Windows) tự chạy test, build,
   đóng gói, cài/gỡ thử bộ cài rồi tạo Release (ghi chú lấy từ mục CHANGELOG). Làm tay thì
   `gh release create vX.Y.Z release/* --notes-file …` (đính kèm **tất cả** tệp trong `release\`). Tên tệp phải giữ đúng: `QTDownloader-<ver>-setup.exe` (bản đã cài tự tải ngầm & cài),
   `QTDownloader-<ver>-win64.zip`, bản sao `TDownload-<ver>-win64.zip` (bản ≤ 1.0.3 chỉ nhận tên này) và
   `SHA256SUMS.txt` (thiếu SHA-256 thì bản cài **không** tự cài). Tag phải dạng `vX.Y.Z` (không dùng pre-release cho
   bản chính: API `releases/latest` bỏ qua pre-release). `INNO_APP_ID` / `AppId` **không bao giờ đổi**.

- Dữ liệu: `%LOCALAPPDATA%\QTDownloader\` (`qtdownloader.db` SQLite WAL, `settings.json`, `logs\qtdownloader.log`,
  `updates\` bộ cài tải ngầm). Bản cài: `%LOCALAPPDATA%\Programs\QT Downloader\`. Lần đầu mở 1.1.0,
  `%LOCALAPPDATA%\TDownload\` được đổi tên sang thư mục mới (`settings.resolve_data_dir`).
  Biến `QTDOWNLOADER_DATA` đổi thư mục dữ liệu — **luôn dùng thư mục tạm khi thử nghiệm** để không đụng dữ liệu thật.
- API cho extension: `127.0.0.1:41888` (`settings.api_port`). Chỉ 1 phiên bản app chạy (QLocalServer
  `QTDownloader-<user>-<hash>`); mở lần 2 kèm URL sẽ chuyển URL sang phiên bản đang chạy.
- Máy chủ thử nghiệm `tests/server.py` mô phỏng: `rate` (KB/s mỗi kết nối), `norange`, `nolen`, `fail` (rớt ngẫu
  nhiên), `maxconn` (503), `cap` (Range ngắn), `ver` (tệp đổi), `weak` (ETag yếu), `/redirect/`, `/cd`
  (Content-Disposition tiếng Việt), `/html`, `/sized/<n>/<tên>[.sha256]`, `/hls/{master,media,enc,live}.m3u8`.

## 4. Kiến trúc

```
Extension MV3 ──HTTP JSON──► core/api_server.py (127.0.0.1, kiểm Host/Origin/CORS)
                                   │
UI (PySide6, luồng chính) ──engine.call()──► core/engine.py (luồng riêng, asyncio loop)
   ▲  QTimer 400 ms đọc engine.snapshot          ├─ http_task.HttpTask  (1 tệp HTTP)
   └── Bridge.event (Qt Signal, queued) ◄─emit───├─ hls.HlsTask         (1 luồng HLS)
                                                 ├─ RateLimiter toàn cục, host_caps, hàng đợi, lịch
                                                 └─ storage.Storage (SQLite) + settings.json
```

| Tệp | Vai trò | Điểm cần biết |
|---|---|---|
| `core/segments.py` | Chia đoạn động thuần (không I/O) | `Segment.pos` = đã nhận (kể cả trong bộ đệm), `written` = đã ghi; lưu theo `written`. `split_largest` cắt nửa sau đoạn lớn nhất, **ưu tiên cắt sau `req_end`** (cửa sổ đang bay) |
| `core/http_task.py` | Tải 1 tệp | Probe `GET Range: bytes=0-0` → so ETag/kích thước với trạng thái cũ → tệp sparse → controller mở dần worker (0,12 s/kết nối) → worker GET theo cửa sổ `speed×4s` (512 KB–64 MB) → hết đoạn thì "cướp" nửa đoạn lớn nhất. Checkpoint 3 s: **chụp vị trí → fsync → lưu**. AIMD: 429/503/ConnectError/403 ở kết nối phụ → giảm `conn_cap`, nhớ theo host, 30 s sau thử tăng lại |
| `core/engine.py` | Điều phối | Mọi API là coroutine, gọi qua `engine.call(fn, …)` (trả `concurrent.futures.Future`). `snapshot` là dict thay mới mỗi 0,4 s (cache theo `_dirty`). `ui_attached=True` → link từ trình duyệt thành sự kiện `browser_add` để UI hiện hộp thoại |
| `core/hls.py` | HLS | Master → chọn biến thể; segment tải song song vào `<tệp>.tdhls/`; ghép; có ffmpeg thì remux `.ts→.mp4`. fMP4 (`#EXT-X-MAP`) → `.mp4` |
| `core/fileio.py` | Ghi tệp | `FSCTL_SET_SPARSE` + `truncate(size)`; ghi bằng lock+seek+write; `mark_of_the_web()` ghi ADS `Zone.Identifier` |
| `core/updater.py` | Báo & tải bản mới | `GET api.github.com/repos/<GITHUB_REPO>/releases/latest`; so `tag_name` với `__version__`; tìm `SETUP_RE` (`QTDownloader-*-setup.exe`), `ASSET_RE` (zip) rồi `LEGACY_ASSET_RE` (`TDownload-*.zip`); `is_installed()` = cạnh exe có `unins000.exe`; `download_verified` (bắt buộc SHA-256, `.part`, sai thì xoá); `cleanup_updates_dir`. Engine: `startup_update` (gọi từ `ui/app.py` mỗi lần mở — test/CLI không gọi nên không ra mạng), `check_update(manual)` (bản cài + `auto_download_updates` → `start_prepare_update` tải ngầm, `update_state` trong snapshot, sự kiện `update_ready`/`update_failed`), `skip_update`, `download_update` (bản zip: thêm vào danh sách tải); `_maybe_check_update` 1 lần/ngày khi chạy liên tục. Repo riêng tư → 404 → báo lỗi êm |
| `installer.iss` + `installer/Vietnamese.isl` | Bộ cài Inno Setup 6 | UTF-8 **có BOM** + CRLF; `AppId` = `INNO_APP_ID`, `AppMutex` = `APP_MUTEX_NAME` (`qtdownloader/__init__.py`, app tạo mutex trong `ui/app.py`), `PrivilegesRequired=lowest`, `{localappdata}\Programs\QT Downloader`, `[Code]` gỡ giao thức/mục Run (tên mới + cũ) và hỏi xoá dữ liệu, cờ `/LAUNCHAPP` mở lại app sau khi cài im lặng. `tests/test_installer.py` đối chiếu với mã |
| `ui/main_window.py` (cập nhật) | Như QT PDF Pro | `update_available` tự động → chỉ thông báo khay + `update_btn`; `update_ready` → nút "Khởi động lại để cập nhật" (`restart_to_update` → `run_after_exit` = bộ cài `/SILENT /LAUNCHAPP`), `quit_app()` cài im lặng khi thoát (`install_update=False` khi lịch hẹn tắt máy); `ui/app.py` chạy `run_after_exit` **sau** `app.exec()` + nhả mutex |
| `core/api_server.py` | HTTP tối giản | `/api/ping` (kèm `protocol` = đã bật `qtdownloader://` chưa), `/api/add`, `/api/add-batch`. POST bắt buộc `application/json` (ép preflight CORS) |
| `core/integration.py` | Tích hợp Windows | Phân tích `qtdownloader://open[?minimized=1]` / `qtdownloader://add?url=…`; đăng ký giao thức (HKCU\Software\Classes) và khởi động cùng Windows (HKCU\…\Run) **chỉ khi người dùng bật tuỳ chọn**; mọi hàm nhận `root`/đường dẫn khoá để test trên khoá tạm. `sync()` lúc mở app ghi lại lệnh nếu app đã chuyển chỗ |
| `ui/main_window.py` | Cửa sổ chính | Toolbar, cây phân loại, bảng (`table_model.py`), khay, clipboard, kéo-thả, nhập `.ef2` |
| `ui/progress_dialog.py` | Cửa sổ tiến trình | `SegmentBar` tô màu theo worker sở hữu đoạn; xử lý "tải xong" nằm ở `MainWindow._on_completed` |
| `ui/dialogs.py` | Hộp thoại | `vi_buttons()`/`ask()` thay chữ nút chuẩn của Qt bằng tiếng Việt |
| `extension/` | MV3 (Chrome/Edge/Cốc Cốc) | `downloads.onDeterminingFilename` (trình duyệt tạm giữ lượt tải, chưa hiện UI) → ping app → nhận: cancel+erase, **không** gọi `suggest()`, POST; không nhận: `suggest()`. Không có API này thì dùng `onCreated`. Cookie lấy **theo từng link** (`chrome.cookies.getAll({url})`). `webRequest.onHeadersReceived` dò HLS/video → `storage.session` theo tab. App tắt: bắt tự động thì để trình duyệt tải; menu/popup gọi `ensureApp` → mở **tab tạm** `launch.html` tự điều hướng tới `qtdownloader://` (không đụng tab người dùng; origin của extension → hộp thoại có ô "Luôn cho phép"), chờ ping 10 s (15 s nếu app từng báo `protocol:true`; `protocol:false` thì bỏ qua) → không được thì `downloads.download` + `warn()` (huy hiệu, tiêu đề, `notifications`) |

Trạng thái mục tải: `queued → connecting → downloading → (merging|verifying) → completed | error | paused`.
Tệp đang tải tên `<tên>.tdpart` cạnh tệp đích; xong thì `os.replace`.

## 5. Quy ước mã

- Thông báo lỗi cho người dùng: `DownloadError("…tiếng Việt…")`; lỗi tạm thời dùng `TransientError`/`ThrottledError`.
- Engine không được chặn event loop: I/O tệp qua `engine.io_pool` (`run_in_executor`), SQLite gọi đồng bộ trong
  luồng loop (ghi nhỏ).
- Trong `HttpTask`, worker kiểm `self.halted` (= dừng | lỗi nặng | chuyển 1 kết nối), **không** kiểm riêng `_stop`.
- Sự kiện engine → UI: payload `DownloadItem` được `Bridge` đổi sang `dict` trước khi qua luồng Qt.
- Test: dùng fixture `engine`/`srv` trong `tests/conftest.py`; đọc snapshot bằng `.get(id, {})` vì snapshot có thể
  chưa kịp có mục mới (tick 0,4 s).

## 6. Rào cản kỹ thuật đã gặp (đừng vấp lại)

| Vấn đề | Nguyên nhân | Cách đã xử lý |
|---|---|---|
| Không có .NET/Rust trên máy phát triển | Máy chỉ có Python 3.14, Node 24 | Viết bằng Python, engine tách khỏi UI để sau này port |
| `os.pwrite` không có trên Windows | API chỉ có trên Unix | `PartFile.write_at` dùng lock + seek + write |
| Ghi ở offset xa trong tệp lớn bị khựng | NTFS điền số 0 từ "valid data length" | Đánh dấu tệp sparse trước khi `truncate` |
| Python in tiếng Việt crash `UnicodeEncodeError` | Console bị chuyển hướng dùng cp1252 | `sys.stdout.reconfigure(encoding="utf-8")` trong CLI/server/script |
| `build.bat` lỗi `'p0"' is not recognized` | `cmd.exe` đọc UTF-8 + xuống dòng LF sai | `.bat` ASCII + CRLF; `.gitattributes` giữ `eol=crlf` |
| Gọi `cmd //c build.bat` từ Git Bash không chạy | Đường dẫn/cwd của cmd | Chạy qua PowerShell: `cmd.exe /c ".\build.bat"` |
| Tiến trình nền chết theo shell | `cmd &` trong Bash tool bị kill khi shell kết thúc | Dùng `run_in_background` của tool |
| Trùng tên `Engine.start()` | Vừa là khởi động engine vừa là "tiếp tục tải" | Đổi thành `Engine.resume(ident)` |
| Không chuyển được sang 1 kết nối khi server bỏ Range | Cờ `_stop` bị dùng chung cho nhiều lý do | Tách thuộc tính `halted` |
| Tạm dừng lúc đang probe làm mất tiến độ cũ | `_finish_stopped` xoá segments khi chưa probe | Cờ `_probed` |
| Tệp nhỏ tải đa kết nối chậm (4,5 s vs lý thuyết 2,5 s) | Mở kết nối 0,25 s/cái; ngưỡng chia cố định 1 MB → đuôi tệp dồn 1 kết nối | Ngưỡng chia động `≈1,5 s × tốc độ trung vị` (tối thiểu 128 KB), mở 0,12 s/cái, cửa sổ đầu 1 MB |
| Chia đoạn làm huỷ kết nối đang chạy | Cắt vào giữa phản hồi đang đọc | Cửa sổ yêu cầu có giới hạn, cắt sau `req_end` |
| Kết nối không được tái dùng | Thoát `aiter_raw` trước khi httpx nhận EndOfMessage | Chỉ `break` khi đoạn bị cắt ngắn; đọc đến hết phản hồi một cách tự nhiên |
| HTTP/2 không tăng tốc | Mọi "kết nối" gộp vào 1 TCP | Mặc định HTTP/1.1; HTTP/2 là tuỳ chọn |
| Cookie có thể rò sang host khác | Header `Cookie` cố định đi theo chuyển hướng / tải hàng loạt dùng cookie của trang | Cookie đặt vào jar theo đúng host; extension lấy cookie theo từng origin của link |
| Qt không có bản dịch tiếng Việt; `&` trong tên tab biến mất | Không có `qtbase_vi.qm`; `&` là mnemonic | `vi_buttons()`/`ask()`; viết `&&` |
| `settings.json` bị bỏ qua | PowerShell `Out-File -Encoding utf8` thêm BOM | Đọc bằng `utf-8-sig` |
| Bản build 151 MB | PyInstaller kéo theo numpy, PIL, `opengl32sw.dll` | `--exclude-module …` + xoá `opengl32sw.dll` → ~90 MB |
| Test extension bằng CDP: `chrome.storage` undefined | Bám nhầm service worker của extension có sẵn trong Edge (Copilot); CDP vào trang extension cần cờ | Chọn target có URL kết thúc `/background.js`; chạy Edge với `--enable-unsafe-extension-debugging` |
| `import()` trong service worker bị cấm | Chuẩn HTML cấm dynamic import trong SW | Gọi tính năng qua `chrome.runtime.sendMessage` từ trang popup |
| `--load-extension` | Chrome bản thương hiệu ≥137 bỏ cờ này; Edge 155 vẫn nhận | Test tự động dùng Edge + hồ sơ tạm `--user-data-dir` |
| Test thỉnh thoảng `KeyError` | Snapshot cập nhật mỗi 0,4 s | Test đọc `.get(id, {})` |
| Test giới hạn 503 thỉnh thoảng trượt | Tệp 4 MB < 2 × ngưỡng chia → không mở kết nối thứ 3 | Tệp thử 12 MB |
| `build.bat` lỗi `PermissionError … qwindows.dll` | `dist\QTDownloader\QTDownloader.exe` đang chạy (người dùng mở) giữ tệp | Không tắt app của người dùng; build ra thư mục khác: `build.bat build\release-dist` |
| Bản thử nghiệm "đánh thức" app đang dùng | Tên QLocalServer chung cho mọi thư mục dữ liệu | Tên gắn hash thư mục dữ liệu (`ui/app.py: server_name`). Khi thử exe vẫn phải đổi `api_port` trong `settings.json` tạm vì app thật giữ cổng 41888 |
| Báo bản mới không chạy với repo riêng tư | API GitHub không đăng nhập trả 404 cho repo private | Repo đã chuyển công khai (2026-10-19); không bao giờ nhúng token vào app. Đã kiểm với GitHub thật: không đăng nhập đọc được `v1.0.0`, SHA-256 khớp |

| Extension không mở được app khi app tắt | HTTP localhost không khởi chạy được tiến trình; native messaging cần registry | Giao thức `qtdownloader://` do người dùng tự bật trong Tuỳ chọn (HKCU, gỡ được). Giao thức **chưa đăng ký** thì Chrome/Edge im lặng (tab `about:blank`, không hộp thoại) → extension nhớ `protocol` từ `/api/ping` để khỏi chờ vô ích |
| Lệnh `pythonw -m qtdownloader` trong registry không chạy | Trình duyệt gọi lệnh với thư mục làm việc bất kỳ → không thấy gói `qtdownloader` | Chạy từ mã nguồn thì lệnh là `pythonw "<repo>\run_qtdownloader.py"` (đường dẫn tuyệt đối) |
| App từ mã nguồn mất 3–4 giây mới mở API | Nhập PySide6 + khởi động engine | Extension chờ ping ≥ 10 giây sau khi mở `qtdownloader://` |
| Test không được ghi registry thật | Quy tắc dự án | Hàm `integration.*` nhận `root`/đường dẫn khoá; test dùng `HKCU\Software\QTDownloaderTest\<uuid>` rồi xoá cả cây. Khi thử tay **không** bật 2 tuỳ chọn trên máy người dùng nếu họ chưa cho phép |
| Heredoc qua Bash tool làm mất một nửa dấu `\` | Công cụ xử lý chuỗi trước khi tới shell | Sửa tệp có `\` (regex JS, đường dẫn Windows, `\n` trong f-string) bằng công cụ Edit, không chèn qua heredoc |
| Thử Edge làm rơi tệp `Unconfirmed *.crdownload` vào `Downloads` thật | Hồ sơ tạm vẫn lưu vào thư mục tải mặc định; Edge giữ tải qua http chờ xác nhận | Soạn sẵn `<hồ sơ>\Default\Preferences` **trước lần chạy đầu** với `download.default_directory` trỏ vào scratchpad; lỡ rồi thì `chrome.downloads.cancel` + `erase` |
| Hộp thoại "Mở QT Downloader?" không có ô "Luôn cho phép" | `tabs.create({url:"qtdownloader://…"})` là điều hướng không có origin khởi tạo | Mở trang `launch.html` của extension rồi trang đó `location.href = "qtdownloader://…"` → hộp thoại có ô "Always allow chrome-extension://…" (đã kiểm Edge 155) |
| Link gửi ngay khi app vừa mở bị mất | `engine.start()` mở API trước khi `MainWindow` nối `bridge.event` | Engine giữ sự kiện trong `_ui_backlog` khi `ui_attached` cho tới `engine.ui_ready()` (gọi cuối `ui/app.py`) |
| Mở lại hồ sơ Edge tạm thì extension `--load-extension` bị tắt (lý do `1<<24`) | Sửa `Preferences` từ ngoài khi hồ sơ đã chạy → Chromium coi là bị can thiệp | Mỗi lần cần tuỳ chọn khác thì tạo hồ sơ tạm mới, soạn `Preferences` trước lần chạy đầu (kể cả `protocol_handler.allowed_origin_protocol_pairs` để giả lập "Luôn cho phép") |
| Hồ sơ Edge tạm bị tự đăng nhập/đồng bộ tài khoản Windows (xuất hiện extension của người dùng) | Edge implicit sign-in | Luôn thêm `--disable-sync`; xoá hồ sơ tạm sau khi thử, không đọc dữ liệu trong đó |
| Thử giao thức thật mà không đụng app thật | Lệnh trong registry không mang theo `QTDOWNLOADER_DATA` | (Được người dùng cho phép) đăng ký tạm với lệnh trỏ vào script đặt `QTDOWNLOADER_DATA` tạm rồi gọi `main()`; thử xong `integration.unregister_protocol()` |
| Windows truyền `qtdownloader://open/?minimized=1` | ShellExecute chuẩn hoá URL, chèn `/` trước `?` | `parse_protocol_url` bỏ `/` thừa ở tên hành động |
| Đổi tên bằng `sed` biến `QTDownloader` thành `QQT Downloaderer` | Tên mới `QTDownloader` **chứa** chuỗi cũ `TDownload` → thay lần hai ăn vào kết quả lần một | Thay tên kỹ thuật trước, rồi kiểm `git grep "QQT\|Downloaderer"`; tên hiển thị "QT Downloader" và tên kỹ thuật "QTDownloader" khác nhau — đừng thay chung |
| Windows 11 chặn bộ cài, không có "Run anyway" | **Smart App Control** (khác SmartScreen) chặn mọi tệp chưa ký + chưa có uy tín | Ký số Authenticode (RSA) qua SignPath Foundation: `QTDownloader.exe` trước khi đóng gói, rồi bộ cài. Người dùng tạm thời: tắt Smart App Control (bật lại được từ bản cập nhật 4/2026) |
| Không đẩy được tag từ phiên Agent đám mây | Proxy git chặn push tag | Chạy tay workflow **Phát hành** (workflow_dispatch, nhập tag) — `gh release create` tự tạo tag ở `GITHUB_SHA` |
| Bộ cài không chạy được khi app còn giữ mutex/tệp | `AppMutex` + `CloseApplications`: bộ cài im lặng gặp app đang mở sẽ hỏi/huỷ | Không chạy bộ cài từ trong app đang sống: lưu lệnh vào `MainWindow.run_after_exit`, `ui/app.py` chạy sau khi engine tắt, QLocalServer đóng và `CloseHandle` mutex |
| App chạy dưới khay mà trình duyệt vẫn hiện hộp thoại/khung tải xuống cạnh hộp thoại QT Downloader | `downloads.onCreated` chạy song song với UI tải của trình duyệt; ping + cancel tới muộn | Bắt ở `downloads.onDeterminingFilename` (listener `return true`, trình duyệt giữ lượt tải chờ `suggest()`); nhận thì cancel+erase và **không** gọi `suggest`. Mọi nhánh không nhận **phải** gọi `suggest()`, kể cả khi lỗi, nếu không lượt tải treo |

Giới hạn **cố hữu** (chấp nhận, không phải bug):
- Không bắt được link từ ứng dụng ngoài trình duyệt (cần driver mạng ký số — không làm).
- Extension chỉ thấy tải xuống sau khi trình duyệt đã bắt đầu; tải từ form POST và `blob:` không chuyển được.
- Đa kết nối vô ích nếu server giới hạn theo IP hoặc không hỗ trợ Range.

## 7. Việc cần làm tiếp (theo thứ tự ưu tiên)

1. **Kiểm thử thực tế**: tải từ ≥ 20 host thật (Google Drive, Fshare, Mediafire, GitHub Releases, CDN VN, link có
   chữ ký hết hạn). Ghi tỉ lệ thành công, so tốc độ với IDM; sửa lỗi phát sinh.
2. **Bảo mật API cục bộ**: hiện mọi tiến trình trên máy đều POST được `/api/add`. Thêm token ghép đôi
   (`X-QTDownloader-Token`) giữa app và extension.
   - Bấm thử menu chuột phải thật khi app tắt trên Chrome/Cốc Cốc (Edge đã thử qua cùng hàm `sendLink`; CDP không
     bấm được menu ngữ cảnh).
3. Quét Windows Defender sau khi tải; tự giải nén; phát hiện trùng lặp; bản portable.
4. Tự làm mới link hết hạn qua extension; chế độ nhường mạng (đo RTT); hồ sơ tốc độ theo giờ.
5. DASH (`.mpd`) + ghép audio/video bằng ffmpeg; tích hợp yt-dlp (tuỳ chọn).
6. ~~Bộ cài Inno Setup + tự cài bản mới~~ (1.1.0). **Ký Authenticode qua SignPath Foundation**: mã & workflow đã sẵn
   sàng, chờ duyệt đơn + cấu hình (`.signpath/README.md`); sau đó cân nhắc ký cả `unins000.exe` (Inno `SignTool`).
   Extension cho Firefox.
   Ký số: máy có `signtool` (SDK 10.0.26100) nhưng **chưa có chứng thư Code Signing**. Dự án đã MIT → có thể xin
   SignPath Foundation (miễn phí, cần build từ CI) hoặc Certum Open Source Code Signing. Token chữ ký số Viettel
   (thuế/hoá đơn) thường không có EKU Code Signing; gốc "Vietnam National Root CA" chỉ được tin trên máy đã cài phần
   mềm CA Việt Nam.
7. CI GitHub Actions (Windows) chạy `pytest` cho mọi PR — cần cho người đóng góp và cho SignPath.
8. Nợ kỹ thuật nhỏ: `RateLimiter` hơi giới hạn quá tay khi nhiều worker; icon không đổi màu khi đổi sáng/tối lúc
   đang chạy; chưa có SOCKS proxy (thiếu `socksio`), FTP, NTLM; chưa đo hiệu năng bảng với hàng nghìn mục.

Danh sách đầy đủ kèm cách làm: [docs/DE_XUAT_TINH_NANG.md](docs/DE_XUAT_TINH_NANG.md).

## 8. Kiểm tra trước khi báo "xong"

- `python -m pytest -q tests` qua hết.
- Thay đổi UI: chạy GUI với `QTDOWNLOADER_DATA` tạm (hoặc script chụp `QWidget.grab()`), xem ảnh, kiểm cả chữ tiếng Việt.
- Thay đổi extension: `node --check extension/*.js`; nếu đổi luồng bắt link thì thử lại trên Edge hồ sơ tạm.
- Thay đổi đóng gói: `build.bat` rồi chạy `dist\QTDownloader\QTDownloader.exe` với `QTDOWNLOADER_DATA` tạm, gửi link qua API.
- Thay đổi bộ cài: `python tools/package_release.py` (ISCC phải không báo lỗi/cảnh báo), cài thử im lặng vào thư mục tạm,
  kiểm mục trong Cài đặt › Ứng dụng, gỡ im lặng → thư mục cài và khoá `…\Uninstall\{60877C1B-…}_is1` biến mất.
- Cập nhật [CHANGELOG.md](CHANGELOG.md) và mục 6/7 của tệp này.

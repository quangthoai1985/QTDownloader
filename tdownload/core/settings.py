"""Cấu hình ứng dụng, lưu dạng JSON trong thư mục dữ liệu."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)

DEFAULT_CAPTURE_EXTS = (
    "3gp 7z aac ace aif apk arj asf avi bin bz2 cab deb dmg exe flac flv gz gzip iso jar lzh m4a m4v mkv mov "
    "mp3 mp4 mpeg mpg msi msix msu ogg ogv pdf pkg ppt pptx qt rar rpm sea sit sitx tar tgz tif tiff wav webm "
    "wma wmv xapk xz z zip zst docx xlsx"
)


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "TDownload"


def default_download_dir() -> str:
    return str(Path.home() / "Downloads" / "TDownload")


@dataclass
class Schedule:
    enabled: bool = False
    start_time: str = "23:00"          # HH:MM
    stop_time: str = ""                # "" = không tự dừng
    days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])  # 0 = thứ Hai
    after_done: str = "none"           # none | exit | shutdown | sleep


@dataclass
class Settings:
    download_dir: str = field(default_factory=default_download_dir)
    use_category_dirs: bool = True
    max_connections: int = 8           # số kết nối tối đa / tệp (IDM: 1–32)
    max_concurrent: int = 3            # số tệp tải đồng thời trong hàng đợi
    global_speed_limit_kb: int = 0     # 0 = không giới hạn
    min_split_kb: int = 1024           # đoạn nhỏ hơn 2× giá trị này thì không chia nữa
    max_retries: int = 10
    timeout: int = 30
    http2: bool = False                # HTTP/1.1 mới thật sự "đa kết nối"
    proxy: str = ""                    # vd http://127.0.0.1:8080
    user_agent: str = DEFAULT_UA
    verify_tls: bool = True
    resume_on_start: bool = True       # tự tiếp tục tệp đang tải dở khi mở lại app
    show_progress_dialog: bool = True
    show_complete_dialog: bool = True
    monitor_clipboard: bool = True
    minimize_to_tray: bool = True
    api_port: int = 41888
    browser_ask: bool = True           # hiện hộp thoại khi trình duyệt chuyển link sang
    capture_exts: str = DEFAULT_CAPTURE_EXTS
    ffmpeg_path: str = ""
    auto_checksum_sidecar: bool = True # tự tìm tệp .sha256 cạnh link để kiểm tra
    check_updates: bool = True         # tự hỏi GitHub Releases mỗi ngày
    update_skip_version: str = ""      # phiên bản người dùng chọn "Bỏ qua"
    last_update_check: float = 0.0
    schedule: Schedule = field(default_factory=Schedule)

    @classmethod
    def load(cls, path: Path) -> "Settings":
        s = cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))  # chịu được BOM (Notepad, PowerShell)
        except (OSError, ValueError):
            return s
        known = {f.name for f in fields(cls)}
        for k, v in raw.items():
            if k == "schedule" and isinstance(v, dict):
                sk = {f.name for f in fields(Schedule)}
                s.schedule = Schedule(**{a: b for a, b in v.items() if a in sk})
            elif k in known:
                setattr(s, k, v)
        return s

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def to_dict(self) -> dict:
        return asdict(self)

    def capture_ext_set(self) -> set[str]:
        return {e.strip().lower().lstrip(".") for e in self.capture_exts.replace(",", " ").split() if e.strip()}

"""Mô hình dữ liệu của một mục tải."""

from __future__ import annotations

import os
import uuid
from dataclasses import asdict, dataclass, field, fields

QUEUED = "queued"
PAUSED = "paused"
CONNECTING = "connecting"
DOWNLOADING = "downloading"
MERGING = "merging"
VERIFYING = "verifying"
COMPLETED = "completed"
ERROR = "error"

ACTIVE = {CONNECTING, DOWNLOADING, MERGING, VERIFYING}

STATUS_TEXT = {
    QUEUED: "Trong hàng đợi",
    PAUSED: "Đã dừng",
    CONNECTING: "Đang kết nối…",
    DOWNLOADING: "Đang tải",
    MERGING: "Đang ghép tệp…",
    VERIFYING: "Đang kiểm tra…",
    COMPLETED: "Hoàn tất",
    ERROR: "Lỗi",
}


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class DownloadItem:
    url: str
    filename: str
    save_dir: str
    id: str = field(default_factory=new_id)
    kind: str = "http"                 # http | hls
    mirrors: list[str] = field(default_factory=list)
    category: str = "general"
    status: str = PAUSED
    error: str = ""
    size: int = -1                     # -1 = chưa biết
    downloaded: int = 0
    resumable: bool | None = None
    final_url: str = ""
    etag: str = ""
    last_modified: str = ""
    content_type: str = ""
    referer: str = ""
    user_agent: str = ""
    cookies: str = ""
    headers: dict = field(default_factory=dict)
    connections: int = 0               # 0 = theo cài đặt chung
    speed_limit_kb: int = 0            # 0 = không giới hạn riêng
    segments: list = field(default_factory=list)   # [[start, end, pos], …]
    checksum: str = ""                 # "sha256:…", "md5:…"
    checksum_ok: bool | None = None
    description: str = ""
    page_url: str = ""
    from_queue: bool = False
    queue_pos: float = 0.0
    created: float = 0.0
    last_try: float = 0.0
    completed: float = 0.0
    hls: dict = field(default_factory=dict)  # variant, tổng/đã xong segment

    @property
    def path(self) -> str:
        return os.path.join(self.save_dir, self.filename)

    @property
    def part_path(self) -> str:
        return self.path + ".tdpart"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DownloadItem":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

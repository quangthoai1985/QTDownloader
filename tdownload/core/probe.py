"""Thăm dò khả năng máy chủ: kích thước, hỗ trợ Range, ETag, tên tệp."""

from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

import httpx

from .util import filename_from_url, sanitize_filename

_CR = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", re.I)
_CR_STAR = re.compile(r"bytes\s+\*/(\d+)", re.I)


class DownloadError(Exception):
    """Lỗi có thông điệp tiếng Việt hiển thị cho người dùng."""

    retryable = False

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class TransientError(DownloadError):
    retryable = True


class ThrottledError(TransientError):
    def __init__(self, message: str, status: int, retry_after: float):
        super().__init__(message, status)
        self.retry_after = retry_after


class ResourceChangedError(DownloadError):
    pass


class RangeIgnoredError(DownloadError):
    pass


def http_error(status: int, retry_after: str | None = None) -> DownloadError:
    if status in (429, 503):
        try:
            ra = float(retry_after) if retry_after else 0.0
        except ValueError:
            ra = 0.0
        return ThrottledError(f"Máy chủ đang giới hạn (HTTP {status})", status, ra)
    if status in (408, 500, 502, 504) or 520 <= status <= 530:
        return TransientError(f"Lỗi máy chủ tạm thời (HTTP {status})", status)
    if status in (401, 407):
        return DownloadError(f"Cần đăng nhập/xác thực (HTTP {status})", status)
    if status == 403:
        return DownloadError("Bị từ chối truy cập (HTTP 403) — link có thể đã hết hạn, "
                             "hãy dùng 'Cập nhật địa chỉ tải'", status)
    if status in (404, 410):
        return DownloadError(f"Không tìm thấy tệp trên máy chủ (HTTP {status})", status)
    return DownloadError(f"Máy chủ trả lỗi HTTP {status}", status)


def parse_content_range(value: str) -> tuple[int, int, int] | None:
    """'bytes 0-99/1000' → (0, 99, 1000); tổng '*' → -1."""
    m = _CR.search(value or "")
    if not m:
        return None
    total = -1 if m.group(3) == "*" else int(m.group(3))
    return int(m.group(1)), int(m.group(2)), total


def parse_content_disposition(value: str) -> str:
    if not value:
        return ""
    m = re.search(r"filename\*\s*=\s*([\w-]*)'[^']*'([^;]+)", value, re.I)
    if m:
        enc = m.group(1) or "utf-8"
        try:
            return unquote(m.group(2).strip().strip('"'), encoding=enc, errors="replace")
        except LookupError:
            return unquote(m.group(2).strip().strip('"'))
    m = re.search(r'filename\s*=\s*"((?:[^"\\]|\\.)*)"', value, re.I) or re.search(
        r"filename\s*=\s*([^;]+)", value, re.I)
    if m:
        name = m.group(1).strip().replace('\\"', '"')
        try:  # nhiều máy chủ gửi UTF-8 thô, httpx giải mã thành latin-1
            name = name.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        return unquote(name) if "%" in name else name
    return ""


@dataclass
class ProbeResult:
    url: str
    final_url: str
    status: int
    size: int
    ranged: bool
    etag: str = ""
    last_modified: str = ""
    content_type: str = ""
    filename: str = ""
    headers: dict = field(default_factory=dict)

    @property
    def strong_etag(self) -> str:
        return self.etag if self.etag and not self.etag.startswith("W/") else ""

    @property
    def validator(self) -> str:
        """Giá trị cho If-Range: chỉ dùng ETag mạnh hoặc Last-Modified (RFC 9110 §13.1.5)."""
        return self.strong_etag or self.last_modified

    @property
    def looks_like_html(self) -> bool:
        return self.content_type.startswith("text/html")

    def to_dict(self) -> dict:
        return {
            "url": self.url, "final_url": self.final_url, "status": self.status, "size": self.size,
            "ranged": self.ranged, "etag": self.etag, "last_modified": self.last_modified,
            "content_type": self.content_type, "filename": self.filename,
        }


def guess_filename(url: str, content_disposition: str, content_type: str) -> str:
    name = sanitize_filename(parse_content_disposition(content_disposition), "") or filename_from_url(url)
    if not name:
        name = "download"
    if "." not in name and content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            name += ext
    return name


async def probe(client: httpx.AsyncClient, url: str, headers: dict | None = None) -> ProbeResult:
    """GET với Range: bytes=0-0 (rẻ hơn và đáng tin hơn HEAD ở nhiều CDN)."""
    h = dict(headers or {})
    h["Range"] = "bytes=0-0"
    h["Accept-Encoding"] = "identity"
    async with client.stream("GET", url, headers=h) as r:
        status = r.status_code
        final_url = str(r.url)
        rh = r.headers
        if status >= 400 and status != 416:
            raise http_error(status, rh.get("retry-after"))
        size = -1
        ranged = False
        if status == 206:
            cr = parse_content_range(rh.get("content-range", ""))
            if cr and cr[0] == 0:
                size = cr[2]
                ranged = size >= 0
        elif status == 416:
            m = _CR_STAR.search(rh.get("content-range", ""))
            size = int(m.group(1)) if m else 0
            ranged = True
        elif status == 200:
            enc = rh.get("content-encoding", "identity").lower()
            cl = rh.get("content-length")
            if cl and cl.isdigit() and enc in ("", "identity"):
                size = int(cl)
        ctype = rh.get("content-type", "").lower()
        return ProbeResult(
            url=url,
            final_url=final_url,
            status=status,
            size=size,
            ranged=ranged,
            etag=rh.get("etag", ""),
            last_modified=rh.get("last-modified", ""),
            content_type=ctype,
            filename=guess_filename(final_url, rh.get("content-disposition", ""), ctype),
            headers=dict(rh),
        )

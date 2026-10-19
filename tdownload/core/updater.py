"""Phát hiện phiên bản mới qua GitHub Releases.

Gọi `GET https://api.github.com/repos/<repo>/releases/latest` (bản phát hành mới nhất, không tính bản nháp
và pre-release), so `tag_name` với `__version__`, tìm tệp `TDownload-<ver>-win64.zip` và mã SHA-256 của nó
trong `SHA256SUMS.txt` để khi tải bản mới bằng chính TDownload thì kiểm được toàn vẹn.

Lưu ý: API không cần đăng nhập chỉ thấy được repo CÔNG KHAI (repo riêng tư trả 404) và giới hạn
60 lượt/giờ/IP — app chỉ tự kiểm tra 1 lần/ngày.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

import httpx

from .. import GITHUB_REPO, __version__

DEFAULT_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ASSET_RE = re.compile(r"^TDownload-.+-win64\.zip$", re.I)


class UpdateCheckError(Exception):
    """Lỗi kiểm tra cập nhật, thông điệp tiếng Việt hiển thị được cho người dùng."""


def parse_version(text: str | None) -> tuple[int, int, int] | None:
    m = re.match(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def is_newer(remote: str | None, local: str = __version__) -> bool:
    r, cur = parse_version(remote), parse_version(local)
    return bool(r and cur and r > cur)


@dataclass
class UpdateInfo:
    version: str
    tag: str
    name: str
    notes: str
    page_url: str
    published: str
    asset_name: str = ""
    asset_url: str = ""
    asset_size: int = 0
    sha256: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


async def fetch_latest(client: httpx.AsyncClient, url: str = DEFAULT_URL) -> UpdateInfo:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"TDownload/{__version__}",
    }
    try:
        r = await client.get(url, headers=headers, timeout=15.0)
    except httpx.HTTPError as e:
        raise UpdateCheckError(f"Không kết nối được GitHub: {e}") from e
    if r.status_code == 404:
        raise UpdateCheckError("Chưa có bản phát hành công khai (repo riêng tư hoặc chưa phát hành bản nào)")
    if r.status_code in (403, 429):
        raise UpdateCheckError("GitHub đang giới hạn lượt kiểm tra — thử lại sau")
    if r.status_code != 200:
        raise UpdateCheckError(f"GitHub trả lỗi HTTP {r.status_code}")
    try:
        d = r.json()
    except ValueError as e:
        raise UpdateCheckError("Phản hồi của GitHub không hợp lệ") from e
    tag = str(d.get("tag_name") or "")
    ver = parse_version(tag)
    if ver is None:
        raise UpdateCheckError(f"Tag phát hành không đúng dạng phiên bản: {tag!r}")
    info = UpdateInfo(
        version="%d.%d.%d" % ver, tag=tag, name=str(d.get("name") or tag), notes=str(d.get("body") or ""),
        page_url=str(d.get("html_url") or ""), published=str(d.get("published_at") or ""),
    )
    assets = [a for a in d.get("assets") or [] if isinstance(a, dict)]
    zip_asset = next((a for a in assets if ASSET_RE.match(str(a.get("name", "")))), None)
    if zip_asset:
        info.asset_name = str(zip_asset["name"])
        info.asset_url = str(zip_asset.get("browser_download_url") or "")
        info.asset_size = int(zip_asset.get("size") or 0)
        sums = next((a for a in assets if str(a.get("name", "")).upper() == "SHA256SUMS.TXT"), None)
        if sums and sums.get("browser_download_url"):
            info.sha256 = await _sha_for(client, sums["browser_download_url"], info.asset_name)
    return info


async def _sha_for(client: httpx.AsyncClient, url: str, name: str) -> str:
    try:
        r = await client.get(url, timeout=15.0)
    except httpx.HTTPError:
        return ""
    if r.status_code != 200 or len(r.content) > 64 * 1024:
        return ""
    for line in r.text.splitlines():
        m = re.match(r"\s*([0-9a-fA-F]{64})\s+\*?(\S+)\s*$", line)
        if m and m.group(2) == name:
            return m.group(1).lower()
    return ""

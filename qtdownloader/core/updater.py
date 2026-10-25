"""Phát hiện phiên bản mới qua GitHub Releases.

Gọi `GET https://api.github.com/repos/<repo>/releases/latest` (bản phát hành mới nhất, không tính bản nháp
và pre-release), so `tag_name` với `__version__`, tìm gói `QTDownloader-<ver>-win64.zip` (bản giải nén chạy ngay) và
bộ cài `QTDownloader-<ver>-setup.exe` cùng mã SHA-256 trong `SHA256SUMS.txt` để khi tải bản mới bằng chính
QT Downloader thì kiểm được toàn vẹn. Bản đã cài bằng bộ cài (`is_installed()`) tải bộ cài; bản giải nén tải gói zip.

Bản phát hành phải kèm thêm bản sao `TDownload-<ver>-win64.zip`: các bản TDownload ≤ 1.0.3 chỉ nhận tên đó.

Lưu ý: API không cần đăng nhập chỉ thấy được repo CÔNG KHAI (repo riêng tư trả 404) và giới hạn
60 lượt/giờ/IP — app tự kiểm tra mỗi lần mở (và 1 lần/ngày nếu chạy liên tục dưới khay).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from .. import APP_ID, GITHUB_REPO, __version__

DEFAULT_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ASSET_RE = re.compile(rf"^{APP_ID}-.+-win64\.zip$", re.I)
LEGACY_ASSET_RE = re.compile(r"^TDownload-.+-win64\.zip$", re.I)
SETUP_RE = re.compile(rf"^{APP_ID}-.+-setup\.exe$", re.I)


def is_installed(exe: str | None = None) -> bool:
    """Bản .exe đang chạy được cài bằng bộ cài Inno Setup (cạnh exe có trình gỡ cài đặt unins000.exe)."""
    if exe is None:
        if not getattr(sys, "frozen", False):
            return False
        exe = sys.executable
    return os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(exe)), "unins000.exe"))


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
    setup_name: str = ""
    setup_url: str = ""
    setup_size: int = 0
    setup_sha256: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


async def fetch_latest(client: httpx.AsyncClient, url: str = DEFAULT_URL) -> UpdateInfo:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"QTDownloader/{__version__}",
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

    def find(rx: re.Pattern) -> dict | None:
        return next((a for a in assets if rx.match(str(a.get("name", "")))), None)

    zip_asset = find(ASSET_RE) or find(LEGACY_ASSET_RE)
    setup = find(SETUP_RE)
    if zip_asset:
        info.asset_name = str(zip_asset["name"])
        info.asset_url = str(zip_asset.get("browser_download_url") or "")
        info.asset_size = int(zip_asset.get("size") or 0)
    if setup:
        info.setup_name = str(setup["name"])
        info.setup_url = str(setup.get("browser_download_url") or "")
        info.setup_size = int(setup.get("size") or 0)
    sums = next((a for a in assets if str(a.get("name", "")).upper() == "SHA256SUMS.TXT"), None)
    if (zip_asset or setup) and sums and sums.get("browser_download_url"):
        table = await _sha_table(client, sums["browser_download_url"])
        info.sha256 = table.get(info.asset_name, "")
        info.setup_sha256 = table.get(info.setup_name, "")
    return info


async def _sha_table(client: httpx.AsyncClient, url: str) -> dict[str, str]:
    """SHA256SUMS.txt → {tên tệp: sha256}."""
    try:
        r = await client.get(url, timeout=15.0)
    except httpx.HTTPError:
        return {}
    if r.status_code != 200 or len(r.content) > 64 * 1024:
        return {}
    out = {}
    for line in r.text.splitlines():
        m = re.match(r"\s*([0-9a-fA-F]{64})\s+\*?(\S+)\s*$", line)
        if m:
            out[m.group(2)] = m.group(1).lower()
    return out


async def download_verified(client: httpx.AsyncClient, url: str, dest: Path, sha256: str, size: int = 0,
                            progress: Callable[[int, int], None] | None = None) -> Path:
    """Tải ngầm bộ cài bản mới về `dest` (qua `.part`), bắt buộc khớp SHA-256 — sai thì xoá, không để lại gì.

    Tệp này sẽ được CHẠY nên không chấp nhận khi bản phát hành thiếu mã SHA-256.
    """
    if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256 or ""):
        raise UpdateCheckError("Bản phát hành thiếu mã SHA-256 cho bộ cài — không tự cài được")
    loop = asyncio.get_running_loop()
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    done = 0
    try:
        async with client.stream("GET", url, timeout=httpx.Timeout(30.0, connect=15.0)) as r:
            if r.status_code != 200:
                raise UpdateCheckError(f"Tải bản cập nhật lỗi HTTP {r.status_code}")
            total = int(r.headers.get("content-length") or size or 0)
            with open(part, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 16):
                    await loop.run_in_executor(None, f.write, chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except httpx.HTTPError as e:
        part.unlink(missing_ok=True)
        raise UpdateCheckError(f"Không tải được bản cập nhật: {e}") from e
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    if h.hexdigest() != sha256.lower():
        part.unlink(missing_ok=True)
        raise UpdateCheckError("Bộ cài tải về sai mã SHA-256 — đã xoá, không cài")
    os.replace(part, dest)
    return dest


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def cleanup_updates_dir(folder: Path, current: str = __version__, keep: str = "") -> None:
    """Xoá bộ cài đã dùng / dở dang: mọi tệp trong thư mục cập nhật trừ bộ cài của bản MỚI HƠN bản đang chạy."""
    if not folder.is_dir():
        return
    for f in folder.iterdir():
        m = SETUP_RE.match(f.name)
        ver = re.search(r"-(\d+\.\d+\.\d+)-setup\.exe$", f.name)
        if f.name == keep or (m and ver and is_newer(ver.group(1), current)):
            continue
        try:
            f.unlink()
        except OSError:
            pass

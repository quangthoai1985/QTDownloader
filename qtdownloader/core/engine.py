"""Engine: quản lý mọi mục tải, hàng đợi, lịch, giới hạn tốc độ và snapshot cho UI.

Engine chạy trong một luồng riêng có event loop asyncio. Giao diện (hoặc CLI) chỉ:
  * gọi `engine.call(engine.add, url, …)` (an toàn đa luồng, trả concurrent Future), và
  * đọc `engine.snapshot` (dict bất biến, được thay mới ~2,5 lần/giây).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import datetime as dt
import logging
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from . import categories
from . import models as M
from .limiter import RateLimiter
from .probe import DownloadError, probe
from .settings import DB_NAME, DEFAULT_UA, LEGACY_DB, Settings, default_data_dir
from .storage import Storage
from . import updater as U
from .updater import DEFAULT_URL as UPDATE_URL, UpdateCheckError, fetch_latest, is_installed, is_newer
from .util import filename_from_url, host_of, now, sanitize_filename, unique_path

log = logging.getLogger("qtdownloader.engine")

MAX_TOTAL_CONNECTIONS = 128
TICK = 0.4
STARTUP_UPDATE_DELAY = 1.0   # giây sau khi cửa sổ hiện mới hỏi GitHub (không làm chậm lúc mở)


def parse_cookie_header(header: str) -> list[tuple[str, str]]:
    out = []
    for part in (header or "").split(";"):
        if "=" in part:
            name, value = part.split("=", 1)
            name = name.strip()
            if name:
                out.append((name, value.strip()))
    return out


class Engine:
    def __init__(self, data_dir: str | Path | None = None, start_api: bool = True):
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.data_dir / "settings.json"
        self.settings = Settings.load(self.settings_path)
        self.items: dict[str, M.DownloadItem] = {}
        self.tasks: dict[str, object] = {}
        self._atasks: dict[str, asyncio.Task] = {}
        self.host_caps: dict[str, int] = {}
        self.limiter = RateLimiter(self.settings.global_speed_limit_kb * 1024)
        self.io_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tdl-io")
        self.listeners: list[Callable[[str, object], None]] = []
        self.ui_attached = False
        # App vừa mở (vd extension mở qua qtdownloader:// rồi gửi link ngay): API đã nhận nhưng cửa sổ chưa nối sự
        # kiện → giữ lại tới khi giao diện gọi ui_ready(), không làm mất link.
        self._ui_backlog: list[tuple[str, object]] | None = []
        self.queue_running = False
        self._queue_by_schedule = False
        self._requeue: set[str] = set()
        self._schedule_fired: str = ""
        self._dirty: set[str] = set()
        self._snap_cache: dict[str, dict] = {}
        self.snapshot: dict = {"version": 0, "items": {}, "queue_running": False, "speed": 0.0}
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self.storage: Storage | None = None
        self.start_api = start_api
        self.api = None
        self.api_error = ""
        self.update_url = os.environ.get("QTDOWNLOADER_UPDATE_URL") or UPDATE_URL
        self.update_info: dict | None = None
        self.installed = is_installed()   # cài bằng bộ cài → cập nhật bằng bộ cài mới thay vì gói zip
        # Tải ngầm bộ cài bản mới: {"stage": downloading|ready|failed, "version", "done", "total", "path", "error"}
        self.update_state: dict | None = None
        self._prepare_task: asyncio.Task | None = None
        self._update_task: asyncio.Task | None = None
        self._boot_time = time.monotonic()

    # ================================================================ vòng đời
    def start(self) -> None:
        ready = threading.Event()
        boot_error: list[BaseException] = []

        def runner():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(self._boot())
            except BaseException as e:  # báo lỗi khởi động cho luồng gọi
                boot_error.append(e)
                ready.set()
                return
            ready.set()
            self.loop.run_forever()
            self.loop.close()

        self.thread = threading.Thread(target=runner, name="tdl-engine", daemon=True)
        self.thread.start()
        ready.wait()
        if boot_error:
            raise boot_error[0]

    async def _boot(self) -> None:
        db = self.data_dir / DB_NAME
        if not db.exists() and (self.data_dir / LEGACY_DB).exists():   # đang dùng tạm thư mục của bản TDownload cũ
            db = self.data_dir / LEGACY_DB
        self.storage = Storage(db)
        resume: list[str] = []
        for d in self.storage.load_all():
            item = M.DownloadItem.from_dict(d)
            if item.status in M.ACTIVE:
                if self.settings.resume_on_start:
                    resume.append(item.id)
                item.status = M.PAUSED
            self.items[item.id] = item
            self._dirty.add(item.id)
        self._ticker = asyncio.create_task(self._tick_loop())
        if self.start_api:
            from .api_server import LocalApiServer
            self.api = LocalApiServer(self, self.settings.api_port)
            try:
                await self.api.start()
            except OSError as e:
                self.api_error = f"Không mở được cổng {self.settings.api_port}: {e}"
                log.warning(self.api_error)
                self.api = None
        for ident in resume:
            self._start_task(ident)

    def shutdown(self, timeout: float = 15.0) -> None:
        if not self.loop or not self.thread:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._shutdown(), self.loop).result(timeout)
        except Exception:
            log.exception("Lỗi khi tắt engine")
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout)
        self.io_pool.shutdown(wait=True)

    async def _shutdown(self) -> None:
        for t in (self._prepare_task, self._update_task):   # tải ngầm dở → xoá .part (xem download_verified)
            if t is not None and not t.done():
                t.cancel()
        active = [i for i in self._atasks]
        await asyncio.gather(*(self._stop_task(i) for i in active), return_exceptions=True)
        for ident in active:  # đánh dấu để lần sau tự tải tiếp (resume_on_start)
            item = self.items.get(ident)
            if item and item.status in (M.PAUSED, M.QUEUED):
                item.status = M.DOWNLOADING
                self.persist(item)
        if self.api:
            await self.api.stop()
        self._ticker.cancel()
        self.storage.close()

    # ================================================================ gọi an toàn đa luồng
    def call(self, fn, *args, **kwargs) -> concurrent.futures.Future:
        return asyncio.run_coroutine_threadsafe(fn(*args, **kwargs), self.loop)

    def call_sync(self, fn, *args, timeout: float = 60, **kwargs):
        return self.call(fn, *args, **kwargs).result(timeout)

    # ================================================================ sự kiện / lưu
    def emit(self, kind: str, payload) -> None:
        if self.ui_attached and self._ui_backlog is not None:
            self._ui_backlog.append((kind, payload))
            return
        for listener in list(self.listeners):
            try:
                listener(kind, payload)
            except Exception:
                log.exception("Listener lỗi với sự kiện %s", kind)

    async def ui_ready(self) -> None:
        """Giao diện đã nối xong sự kiện → phát lại những sự kiện đến sớm (link từ trình duyệt…)."""
        backlog, self._ui_backlog = self._ui_backlog or [], None
        for kind, payload in backlog:
            self.emit(kind, payload)

    def changed(self, item: M.DownloadItem, persist: bool = False) -> None:
        self._dirty.add(item.id)
        if persist:
            self.persist(item)

    def persist(self, item: M.DownloadItem) -> None:
        if item.id in self.items and self.storage is not None:
            self.storage.save(item.to_dict())

    def requeue_on_stop(self, item: M.DownloadItem) -> bool:
        if item.id in self._requeue:
            self._requeue.discard(item.id)
            return True
        return False

    def connection_budget(self) -> int:
        used = sum(len(getattr(t, "workers", {})) for t in self.tasks.values())
        return MAX_TOTAL_CONNECTIONS - used

    def make_client(self, item: M.DownloadItem | None = None, *, url: str = "", referer: str = "",
                    cookies: str = "", user_agent: str = "", headers: dict | None = None,
                    http2: bool | None = None) -> httpx.AsyncClient:
        s = self.settings
        if item is not None:
            url, referer, cookies = item.url, item.referer, item.cookies
            user_agent, headers = item.user_agent, item.headers
        h = {
            "User-Agent": user_agent or s.user_agent or DEFAULT_UA,
            "Accept": "*/*",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        }
        if referer:
            h["Referer"] = referer
        h.update(headers or {})
        client = httpx.AsyncClient(
            http2=s.http2 if http2 is None else http2,
            follow_redirects=True,
            max_redirects=10,
            timeout=httpx.Timeout(s.timeout, connect=min(20, s.timeout)),
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=32, keepalive_expiry=30),
            proxy=s.proxy or None,
            verify=s.verify_tls,
            headers=h,
            trust_env=not s.proxy,
        )
        # Cookie gắn với đúng host gốc → không rò rỉ sang CDN khác khi bị chuyển hướng
        host = host_of(url)
        for name, value in parse_cookie_header(cookies):
            client.cookies.set(name, value, domain=host)
        return client

    # ================================================================ API công khai (coroutine)
    async def probe_url(self, url: str, referer: str = "", cookies: str = "", user_agent: str = "",
                        headers: dict | None = None) -> dict:
        async with self.make_client(url=url, referer=referer, cookies=cookies,
                                    user_agent=user_agent, headers=headers, http2=False) as c:
            if url.split("?", 1)[0].lower().endswith(".m3u8"):
                from .hls import probe_hls
                return await probe_hls(c, url)
            res = await probe(c, url)
            d = res.to_dict()
            if d["content_type"] in ("application/vnd.apple.mpegurl", "application/x-mpegurl",
                                     "audio/mpegurl", "audio/x-mpegurl"):
                from .hls import probe_hls
                return await probe_hls(c, url)
            d["kind"] = "http"
            return d

    async def add(self, url: str, *, filename: str = "", save_dir: str = "", category: str = "",
                  referer: str = "", cookies: str = "", user_agent: str = "", headers: dict | None = None,
                  mirrors: list[str] | None = None, connections: int = 0, start: bool = True,
                  queue: bool = False, checksum: str = "", description: str = "", page_url: str = "",
                  kind: str = "http", size: int = -1, hls: dict | None = None,
                  speed_limit_kb: int = 0) -> str:
        url = url.strip()
        if not url.lower().startswith(("http://", "https://")):
            raise DownloadError("Chỉ hỗ trợ địa chỉ http:// hoặc https://")
        if kind == "http" and url.split("?", 1)[0].lower().endswith(".m3u8"):
            kind = "hls"
        name = sanitize_filename(filename) if filename else (filename_from_url(url) or "download")
        if kind == "hls" and not os.path.splitext(name)[1].lower() in (".ts", ".mp4"):
            name = os.path.splitext(name)[0] + ".ts"
        category = category or categories.category_for(name)
        if not save_dir:
            save_dir = self.settings.download_dir
            if self.settings.use_category_dirs:
                save_dir = os.path.join(save_dir, categories.subdir(category))
        taken = {i.path for i in self.items.values() if i.status != M.COMPLETED}
        os.makedirs(save_dir, exist_ok=True)
        name = unique_path(save_dir, name, taken)
        item = M.DownloadItem(
            url=url, filename=name, save_dir=save_dir, kind=kind, category=category, referer=referer,
            cookies=cookies, user_agent=user_agent, headers=dict(headers or {}),
            mirrors=[m.strip() for m in (mirrors or []) if m.strip()], connections=connections,
            checksum=checksum.strip(), description=description, page_url=page_url, size=size,
            created=now(), status=M.QUEUED if queue else M.PAUSED, hls=dict(hls or {}),
            speed_limit_kb=speed_limit_kb,
        )
        item.queue_pos = max((i.queue_pos for i in self.items.values()), default=0) + 1
        self.items[item.id] = item
        self.changed(item, persist=True)
        self.emit("added", item)
        if start and not queue:
            self._start_task(item.id)
        return item.id

    async def resume(self, ident: str) -> None:
        item = self.items.get(ident)
        if item and item.status != M.COMPLETED:
            item.from_queue = False
            self._start_task(ident)

    async def pause(self, ident: str) -> None:
        await self._stop_task(ident)

    async def set_queued(self, ident: str, queued: bool) -> None:
        item = self.items.get(ident)
        if not item or item.status == M.COMPLETED:
            return
        if queued:
            if ident in self._atasks:
                self._requeue.add(ident)
                await self._stop_task(ident)
            item.status = M.QUEUED
        elif item.status == M.QUEUED:
            item.status = M.PAUSED
        self.changed(item, persist=True)

    async def remove(self, ident: str, delete_file: bool = False) -> None:
        await self._stop_task(ident)
        item = self.items.pop(ident, None)
        if not item:
            return
        await asyncio.get_running_loop().run_in_executor(self.io_pool, _remove_files, item, delete_file)
        self.storage.delete(ident)
        self._snap_cache.pop(ident, None)
        self.emit("removed", item)

    async def restart(self, ident: str) -> None:
        item = self.items.get(ident)
        if not item:
            return
        await self._stop_task(ident)
        await asyncio.get_running_loop().run_in_executor(self.io_pool, _remove_files, item, False)
        item.segments, item.downloaded, item.error, item.checksum_ok = [], 0, "", None
        item.hls.pop("done", None)
        if item.status == M.COMPLETED:
            item.completed = 0
            name = unique_path(item.save_dir, item.filename) if os.path.exists(item.path) else item.filename
            item.filename = name
        item.status = M.PAUSED
        self.changed(item, persist=True)
        self._start_task(ident)

    async def refresh_url(self, ident: str, new_url: str, referer: str = "", cookies: str = "") -> str:
        """'Cập nhật địa chỉ tải' cho link hết hạn: chỉ nhận link mới nếu cùng kích thước."""
        item = self.items.get(ident)
        if not item:
            return "Không tìm thấy mục tải"
        info = await self.probe_url(new_url, referer or item.referer, cookies or item.cookies, item.user_agent)
        if item.size > 0 and info.get("size") != item.size:
            return f"Link mới có kích thước khác ({info.get('size')} ≠ {item.size}) — không phải cùng tệp"
        await self._stop_task(ident)
        item.url = new_url
        if referer:
            item.referer = referer
        if cookies:
            item.cookies = cookies
        item.error = ""
        self.changed(item, persist=True)
        self._start_task(ident)
        return ""

    async def set_speed_limit(self, ident: str, kb: int) -> None:
        item = self.items.get(ident)
        if not item:
            return
        item.speed_limit_kb = max(0, int(kb))
        task = self.tasks.get(ident)
        if task is not None:
            task.set_speed_limit(item.speed_limit_kb)
        self.changed(item, persist=True)

    async def update_item(self, ident: str, **fields) -> None:
        item = self.items.get(ident)
        if not item:
            return
        for k in ("description", "checksum", "connections", "referer", "cookies", "mirrors"):
            if k in fields:
                setattr(item, k, fields[k])
        self.changed(item, persist=True)

    async def update_settings(self, values: dict) -> None:
        from dataclasses import fields as dc_fields
        from .settings import Schedule
        known = {f.name for f in dc_fields(Settings)}
        for k, v in values.items():
            if k == "schedule" and isinstance(v, dict):
                self.settings.schedule = Schedule(**v)
            elif k in known:
                setattr(self.settings, k, v)
        self.settings.save(self.settings_path)
        self.limiter.set_rate(self.settings.global_speed_limit_kb * 1024)

    async def pause_all(self) -> None:
        await asyncio.gather(*(self._stop_task(i) for i in list(self._atasks)), return_exceptions=True)

    async def resume_all(self) -> None:
        for item in list(self.items.values()):
            if item.status in (M.PAUSED, M.ERROR):
                self._start_task(item.id)

    async def start_queue(self, by_schedule: bool = False) -> None:
        self.queue_running = True
        self._queue_by_schedule = by_schedule
        self._process_queue()

    async def stop_queue(self) -> None:
        self.queue_running = False
        stops = []
        for ident, item in self.items.items():
            if ident in self._atasks and item.from_queue:
                self._requeue.add(ident)
                stops.append(self._stop_task(ident))
        await asyncio.gather(*stops, return_exceptions=True)

    async def move_in_queue(self, ident: str, delta: int) -> None:
        queued = sorted((i for i in self.items.values() if i.status != M.COMPLETED), key=lambda i: i.queue_pos)
        idx = next((n for n, i in enumerate(queued) if i.id == ident), None)
        if idx is None:
            return
        j = max(0, min(len(queued) - 1, idx + delta))
        if j == idx:
            return
        queued[idx].queue_pos, queued[j].queue_pos = queued[j].queue_pos, queued[idx].queue_pos
        self.changed(queued[idx], persist=True)
        self.changed(queued[j], persist=True)

    # ---------------------------------------------------------------- cập nhật phiên bản
    async def check_update(self, manual: bool = False) -> dict:
        """Hỏi GitHub Releases. Trả {status: newer|latest|error, info?, error?}.

        Có bản mới → phát sự kiện `update_available` (trừ khi tự kiểm tra mà người dùng đã bỏ qua bản đó).
        """
        self.settings.last_update_check = time.time()
        self.settings.save(self.settings_path)
        try:
            async with self.make_client(http2=False) as c:
                info = await fetch_latest(c, self.update_url)
        except UpdateCheckError as e:
            log.info("Kiểm tra cập nhật: %s", e)
            return {"status": "error", "error": str(e)}
        if not is_newer(info.version):
            return {"status": "latest", "info": info.to_dict()}
        d = info.to_dict()
        self.update_info = d
        skipped = not manual and info.version == self.settings.update_skip_version
        if not skipped:
            auto = (not manual and self.settings.auto_download_updates and self.installed
                    and bool(info.setup_url) and bool(info.setup_sha256))
            self.emit("update_available", d | {"manual": manual, "auto_download": auto})
            if auto:
                self.start_prepare_update()
        return {"status": "newer", "info": d}

    async def skip_update(self, version: str) -> None:
        self.settings.update_skip_version = version
        self.settings.save(self.settings_path)
        if self.update_info and self.update_info.get("version") == version:
            self.update_info = None

    async def download_update(self) -> str:
        """Tải bản mới bằng chính QT Downloader, kèm kiểm SHA-256 từ SHA256SUMS.txt của Release.

        Bản đã cài → tải bộ cài (`QTDownloader-<ver>-setup.exe`, giao diện đề nghị chạy ngay); bản giải nén (hoặc
        bản phát hành chưa có bộ cài) → tải gói zip để người dùng giải nén đè.
        """
        info = self.update_info
        if not info or not (info.get("asset_url") or info.get("setup_url")):
            raise DownloadError("Bản phát hành không có gói cài đặt cho Windows")
        use_setup = bool(info.get("setup_url")) and (self.installed or not info.get("asset_url"))
        url, name, sha, size = ((info["setup_url"], info["setup_name"], info.get("setup_sha256"), info.get("setup_size"))
                                if use_setup else
                                (info["asset_url"], info["asset_name"], info.get("sha256"), info.get("asset_size")))
        return await self.add(
            url, filename=name,
            save_dir=os.path.join(self.settings.download_dir, "QTDownloader-updates"),
            checksum=("sha256:" + sha) if sha else "",
            description=f"Bản cập nhật QT Downloader {info['version']}", size=size or -1,
        )

    # ---- tải ngầm bộ cài (như QT PDF Pro: báo ngay → tải ngầm → "Khởi động lại để cập nhật" / cài khi thoát)
    @property
    def updates_dir(self) -> Path:
        return self.data_dir / "updates"

    def start_prepare_update(self) -> bool:
        """Bắt đầu tải ngầm bộ cài của `update_info` (không hiện trong danh sách tải). False nếu không có bộ cài."""
        info = self.update_info
        if not info or not info.get("setup_url"):
            return False
        st = self.update_state
        if st and st.get("version") == info["version"] and st["stage"] in ("downloading", "ready"):
            return True
        if self._prepare_task is not None and not self._prepare_task.done():
            return True
        self._prepare_task = asyncio.get_running_loop().create_task(self._prepare_update(dict(info)))
        return True

    async def prepare_update(self) -> bool:
        """Cho giao diện gọi qua engine.call (nút "Tải bản mới" ở bản đã cài)."""
        return self.start_prepare_update()

    async def _prepare_update(self, info: dict) -> None:
        ver = info["version"]
        dest = self.updates_dir / info["setup_name"]
        self.update_state = {"stage": "downloading", "version": ver, "done": 0, "total": info.get("setup_size") or 0}

        def progress(done: int, total: int) -> None:
            self.update_state = {"stage": "downloading", "version": ver, "done": done, "total": total}
        try:
            await self.loop.run_in_executor(self.io_pool, U.cleanup_updates_dir, self.updates_dir, U.__version__,
                                            info["setup_name"])
            sha = info.get("setup_sha256") or ""
            if not (dest.exists() and await self.loop.run_in_executor(self.io_pool, U.file_sha256, dest) == sha):
                async with self.make_client(http2=False) as c:
                    await U.download_verified(c, info["setup_url"], dest, sha, info.get("setup_size") or 0, progress)
        except UpdateCheckError as e:
            log.warning("Tải ngầm bản %s: %s", ver, e)
            self.update_state = {"stage": "failed", "version": ver, "error": str(e)}
            self.emit("update_failed", self.update_state)
            return
        except asyncio.CancelledError:
            self.update_state = None
            raise
        except OSError as e:
            self.update_state = {"stage": "failed", "version": ver, "error": f"Không ghi được bộ cài: {e}"}
            self.emit("update_failed", self.update_state)
            return
        self.update_state = {"stage": "ready", "version": ver, "path": str(dest)}
        self.emit("update_ready", self.update_state)

    async def startup_update(self, delay: float = STARTUP_UPDATE_DELAY) -> dict:
        """Gọi một lần khi giao diện đã mở (ui/app.py — test và CLI không gọi nên không hỏi GitHub).

        Trả {"updated_from": phiên bản cũ | ""} để báo "Đã cập nhật"; dọn bộ cài đã dùng; hẹn kiểm tra bản mới.
        """
        prev = self.settings.last_run_version
        if prev != U.__version__:
            self.settings.last_run_version = U.__version__
            self.settings.save(self.settings_path)
        await self.loop.run_in_executor(self.io_pool, U.cleanup_updates_dir, self.updates_dir)
        if self.settings.check_updates:
            async def later():
                await asyncio.sleep(delay)
                await self.check_update(manual=False)
            self._update_task = asyncio.get_running_loop().create_task(later())
        return {"updated_from": prev if prev and is_newer(U.__version__, prev) else ""}

    def _maybe_check_update(self) -> None:
        """App chạy liên tục (dưới khay): kiểm tra lại 1 lần/ngày, chỉ khi có giao diện (CLI và test không gọi)."""
        if not (self.ui_attached and self.settings.check_updates):
            return
        if self._update_task is not None and not self._update_task.done():
            return
        if time.monotonic() - self._boot_time < 20:   # để app khởi động xong đã
            return
        if time.time() - self.settings.last_update_check < 24 * 3600:
            return
        self._update_task = asyncio.get_running_loop().create_task(self.check_update(manual=False))

    async def handle_browser_add(self, payload: dict) -> None:
        """Gọi bởi API cục bộ khi extension chuyển link sang."""
        if self.ui_attached and (self.settings.browser_ask or payload.get("batch")):
            self.emit("browser_batch" if payload.get("batch") else "browser_add", payload)
            return
        for it in payload.get("items") or [payload]:
            try:
                # cookie chỉ lấy theo từng link (cookie của trang có thể thuộc host khác)
                await self.add(it.get("url", ""), filename=it.get("filename", ""),
                               referer=it.get("referer") or payload.get("referer", ""),
                               cookies=it.get("cookies", ""),
                               user_agent=it.get("userAgent") or payload.get("userAgent", ""),
                               page_url=payload.get("pageUrl", ""), kind=it.get("kind", "http"),
                               size=int(it.get("fileSize") or -1))
            except DownloadError as e:
                log.warning("Bỏ qua link từ trình duyệt: %s", e)

    # ================================================================ nội bộ
    def _start_task(self, ident: str) -> None:
        item = self.items.get(ident)
        if item is None or ident in self._atasks or item.status == M.COMPLETED:
            return
        if item.kind == "hls":
            from .hls import HlsTask
            task = HlsTask(self, item)
        else:
            from .http_task import HttpTask
            task = HttpTask(self, item)
        self.tasks[ident] = task
        at = asyncio.get_running_loop().create_task(task.run(), name=f"tdl-{ident}")
        self._atasks[ident] = at

        def done(_t, ident=ident):
            self._atasks.pop(ident, None)
            self.tasks.pop(ident, None)
            self._dirty.add(ident)
            if self.queue_running:
                self._process_queue()

        at.add_done_callback(done)

    async def _stop_task(self, ident: str) -> None:
        at = self._atasks.get(ident)
        task = self.tasks.get(ident)
        if at is None:
            return
        if task is not None:
            task.stop()
        done, _ = await asyncio.wait({at}, timeout=8.0)
        if not done:
            at.cancel()
            await asyncio.gather(at, return_exceptions=True)

    def _process_queue(self) -> None:
        if not self.queue_running:
            return
        active = len(self._atasks)
        waiting = sorted((i for i in self.items.values() if i.status == M.QUEUED and i.id not in self._atasks),
                         key=lambda i: i.queue_pos)
        for item in waiting:
            if active >= max(1, self.settings.max_concurrent):
                break
            item.from_queue = True
            self._start_task(item.id)
            active += 1
        if not waiting and not any(self.items[i].from_queue for i in self._atasks if i in self.items):
            by_schedule = self._queue_by_schedule
            self.queue_running = False
            self._queue_by_schedule = False
            self.emit("queue_finished", {"by_schedule": by_schedule,
                                         "after_done": self.settings.schedule.after_done})

    def _check_schedule(self) -> None:
        sch = self.settings.schedule
        if not sch.enabled:
            return
        t = dt.datetime.now()
        stamp = t.strftime("%Y-%m-%d %H:%M")
        hm = t.strftime("%H:%M")
        if stamp == self._schedule_fired:
            return
        if hm == sch.start_time and t.weekday() in sch.days and not self.queue_running:
            self._schedule_fired = stamp
            asyncio.get_running_loop().create_task(self.start_queue(by_schedule=True))
            self.emit("message", "Đến giờ hẹn: bắt đầu hàng đợi")
        elif sch.stop_time and hm == sch.stop_time and self.queue_running:
            self._schedule_fired = stamp
            asyncio.get_running_loop().create_task(self.stop_queue())
            self.emit("message", "Đến giờ hẹn: dừng hàng đợi")

    async def _tick_loop(self) -> None:
        while True:
            try:
                self._build_snapshot()
                self._process_queue()
                self._check_schedule()
                self._maybe_check_update()
            except Exception:
                log.exception("Lỗi trong vòng tick")
            await asyncio.sleep(TICK)

    def _build_snapshot(self) -> None:
        total_speed = 0.0
        for ident, item in self.items.items():
            task = self.tasks.get(ident)
            if task is not None or ident in self._dirty or ident not in self._snap_cache:
                snap = item_snapshot(item, task)
                total_speed += snap["speed"]
                self._snap_cache[ident] = snap
        self._dirty.clear()
        for ident in list(self._snap_cache):
            if ident not in self.items:
                del self._snap_cache[ident]
        self.snapshot = {
            "version": self.snapshot["version"] + 1,
            "items": dict(self._snap_cache),
            "queue_running": self.queue_running,
            "speed": total_speed,
            "active": len(self._atasks),
            "api_error": self.api_error,
            "update": self.update_info,
            "update_state": self.update_state,
        }


def item_snapshot(item: M.DownloadItem, task) -> dict:
    speed = getattr(task, "speed", 0.0) if task is not None else 0.0
    downloaded = item.downloaded
    size = item.size
    conns: list[dict] = []
    segs: list[list] = []
    if task is not None:
        segmap = getattr(task, "segmap", None)
        if segmap is not None and getattr(task, "ranged", False):
            segs = [[s.start, s.end, s.pos, s.worker] for s in segmap.segs]
        elif getattr(task, "single_seg", None) is not None:
            s = task.single_seg
            segs = [[s.start, max(s.end, s.pos), s.pos, 1]]
        for w in sorted(task.workers.values(), key=lambda w: w.wid):
            seg = w.seg
            conns.append({
                "wid": w.wid, "speed": w.speed, "state": w.state, "total": w.total,
                "range": [seg.start, seg.end, seg.pos] if seg else None,
            })
    elif item.segments:
        segs = [[s, e, p, None] for s, e, p in item.segments]
    progress = None
    if item.status == M.COMPLETED:
        progress = 1.0
    elif item.kind == "hls" and item.hls.get("total"):
        progress = len(item.hls.get("done", [])) / item.hls["total"]
    elif size > 0:
        progress = min(1.0, downloaded / size)
    eta = None
    if speed > 0:
        if size > 0:
            eta = max(0, size - downloaded) / speed
        elif item.kind == "hls" and progress:
            eta = (downloaded / progress - downloaded) / speed
    status_text = M.STATUS_TEXT.get(item.status, item.status)
    if item.status == M.DOWNLOADING and progress is not None:
        status_text = f"{progress * 100:.1f}%"
    return {
        "id": item.id, "kind": item.kind, "url": item.url, "filename": item.filename,
        "save_dir": item.save_dir, "path": item.path, "size": size, "downloaded": downloaded,
        "status": item.status, "status_text": status_text, "error": item.error,
        "message": getattr(task, "message", "") if task is not None else "",
        "speed": speed, "eta": eta, "progress": progress, "category": item.category,
        "resumable": item.resumable, "created": item.created, "last_try": item.last_try,
        "completed": item.completed, "description": item.description, "referer": item.referer,
        "connections_max": item.connections, "speed_limit_kb": item.speed_limit_kb,
        "checksum": item.checksum, "checksum_ok": item.checksum_ok, "queue_pos": item.queue_pos,
        "segments": segs, "conns": conns, "active": task is not None, "mirrors": list(item.mirrors),
        "hls": {k: v for k, v in item.hls.items() if k != "done"} | {"done_count": len(item.hls.get("done", []))},
    }


def _remove_files(item: M.DownloadItem, delete_final: bool) -> None:
    import shutil
    for p in (item.part_path,):
        try:
            os.remove(p)
        except OSError:
            pass
    shutil.rmtree(item.path + ".tdhls", ignore_errors=True)
    if delete_final and item.status == M.COMPLETED:
        try:
            os.remove(item.path)
        except OSError:
            pass

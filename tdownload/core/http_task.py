"""Tải một tệp HTTP/HTTPS bằng nhiều kết nối với chia đoạn động.

Luồng chạy:
  probe → kiểm tra với trạng thái đã lưu (ETag/kích thước) → mở tệp sparse →
  bộ điều khiển (NeedNewConnection) mở dần kết nối → mỗi worker:
      lấy đoạn → GET Range theo cửa sổ thích nghi → ghi vào đúng offset →
      xong đoạn thì "cướp" nửa sau đoạn lớn nhất (tái dùng kết nối keep-alive)
  → checkpoint định kỳ (fsync rồi mới lưu vị trí) → đổi tên .tdpart → kiểm tra checksum.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
import re
import shutil
import time

import httpx

from . import models as M
from .fileio import PartFile, mark_of_the_web
from .limiter import RateLimiter
from .probe import (
    DownloadError,
    RangeIgnoredError,
    ResourceChangedError,
    ThrottledError,
    TransientError,
    http_error,
    parse_content_range,
    probe,
)
from .segments import Segment, SegmentMap
from .util import fmt_size, host_of, now, unique_path

log = logging.getLogger("tdownload.http")

READ_CHUNK = 64 * 1024
FLUSH_SIZE = 512 * 1024
MIN_WINDOW = 512 * 1024
INITIAL_WINDOW = 1024 * 1024
MAX_WINDOW = 64 * 1024 * 1024
WINDOW_SECONDS = 4.0
TAIL_MIN_SPLIT = 128 * 1024
CHECKPOINT_EVERY = 3.0
SPAWN_INTERVAL = 0.12
CAP_RECOVER_AFTER = 30.0

NET_ERRORS = (httpx.TransportError, httpx.StreamError, OSError)


class WorkerInfo:
    __slots__ = ("wid", "task", "seg", "url", "speed", "bytes_tick", "state", "failures", "total")

    def __init__(self, wid: int, url: str):
        self.wid = wid
        self.task: asyncio.Task | None = None
        self.seg: Segment | None = None
        self.url = url
        self.speed = 0.0
        self.bytes_tick = 0
        self.state = "Đang kết nối…"
        self.failures = 0
        self.total = 0


def _short(e: BaseException) -> str:
    msg = str(e) or type(e).__name__
    return msg if len(msg) < 120 else msg[:117] + "…"


class HttpTask:
    def __init__(self, engine, item: M.DownloadItem):
        self.engine = engine
        self.item = item
        self.settings = engine.settings
        self.loop = asyncio.get_running_loop()
        self.client: httpx.AsyncClient | None = None
        self.part = PartFile(item.part_path)
        self.segmap: SegmentMap | None = None
        self.single_seg: Segment | None = None
        self.workers: dict[int, WorkerInfo] = {}
        self.limiter = RateLimiter(item.speed_limit_kb * 1024)
        self.urls: list[str] = []
        self.ranged = False
        self.validator = ""
        self.max_conn = 1
        self.conn_cap = 1
        self.min_split = 1024 * 1024
        self.speed = 0.0
        self.received_total = 0
        self.message = ""
        self._stop = False
        self._probed = False
        self._fatal: DownloadError | None = None
        self._switch_single = False
        self._wake = asyncio.Event()
        self._next_wid = 1
        self._last_spawn = 0.0
        self._last_tick = time.monotonic()
        self._last_bytes = 0
        self._last_cap_cut = 0.0
        self._backoff_until = 0.0

    @property
    def halted(self) -> bool:
        return self._stop or self._fatal is not None or self._switch_single

    # ================= điều khiển từ engine =================
    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def set_speed_limit(self, kb: int) -> None:
        self.item.speed_limit_kb = kb
        self.limiter.set_rate(kb * 1024)

    # ================= vòng đời =================
    async def run(self) -> None:
        item = self.item
        item.status = M.CONNECTING
        item.error = ""
        item.last_try = now()
        self.engine.changed(item)
        try:
            self.client = self.engine.make_client(item)
            res = await self._probe_with_retry(item.url)
            if self._stop:
                return await self._finish_stopped()
            await self._apply_probe(res)
            await self._prepare_file()
            item.status = M.DOWNLOADING
            self.engine.changed(item)
            if self.ranged and item.size > 0:
                await self._run_multi()
                if self._switch_single and not self._stop and not self._fatal:
                    log.info("%s: máy chủ bỏ qua Range → chuyển sang 1 kết nối", item.filename)
                    self.ranged = False
                    item.resumable = False
                    item.segments = []
                    await self.loop.run_in_executor(self.engine.io_pool, self.part.truncate, 0)
                    await self._run_single()
            elif item.size == 0:
                pass
            else:
                await self._run_single()
            if self._fatal:
                raise self._fatal
            if self._stop:
                return await self._finish_stopped()
            await self._finalize()
        except asyncio.CancelledError:
            self._stop = True
            await self._stop_workers()
            await self._finish_stopped()
            raise
        except DownloadError as e:
            await self._finish_error(str(e))
        except NET_ERRORS as e:
            await self._finish_error(f"Lỗi mạng: {_short(e)}")
        except Exception as e:  # lỗi lập trình: không làm sập engine
            log.exception("Lỗi không mong đợi khi tải %s", item.url)
            await self._finish_error(f"Lỗi nội bộ: {_short(e)}")
        finally:
            await self._stop_workers()
            if self.client is not None:
                await self.client.aclose()
            await self.loop.run_in_executor(self.engine.io_pool, self.part.close)

    async def _probe_with_retry(self, url: str):
        attempt = 0
        while True:
            try:
                return await probe(self.client, url)
            except (TransientError, *NET_ERRORS) as e:
                attempt += 1
                if attempt > self.settings.max_retries or self._stop:
                    if isinstance(e, DownloadError):
                        raise
                    raise DownloadError(f"Không kết nối được máy chủ: {_short(e)}") from e
                self.message = f"Không kết nối được ({_short(e)}), thử lại lần {attempt}…"
                await self._sleep(min(30.0, 2 ** (attempt - 1)))

    async def _apply_probe(self, res) -> None:
        item = self.item
        if res.looks_like_html and not os.path.splitext(item.filename)[1].lower().startswith(".htm"):
            self.message = "Cảnh báo: máy chủ trả về trang web (text/html) — có thể là trang đăng nhập/lỗi"
        if item.segments:
            changed = (
                res.size != item.size
                or not res.ranged
                or (item.etag and res.strong_etag and item.etag != res.etag)
            )
            if changed:
                self.message = "Tệp trên máy chủ đã thay đổi hoặc không hỗ trợ tải tiếp — tải lại từ đầu"
                item.segments = []
        item.size = res.size
        item.resumable = res.ranged
        item.final_url = res.final_url
        item.etag = res.etag
        item.last_modified = res.last_modified
        item.content_type = res.content_type
        self.ranged = res.ranged
        self.validator = res.validator
        self._probed = True
        self.urls = [res.final_url or item.url]
        if item.mirrors and self.ranged:
            self.urls += await self._probe_mirrors(res.size)

    async def _probe_mirrors(self, size: int) -> list[str]:
        """Nguồn phụ chỉ được dùng nếu cùng kích thước và hỗ trợ Range (không trộn dữ liệu khác nhau)."""
        async def one(u):
            try:
                r = await probe(self.client, u)
                return r.final_url if r.ranged and r.size == size else None
            except Exception:
                return None
        found = await asyncio.gather(*(one(u) for u in self.item.mirrors))
        good = [u for u in found if u]
        if len(good) < len(self.item.mirrors):
            self.message = f"Dùng {len(good)}/{len(self.item.mirrors)} nguồn phụ (nguồn khác kích thước hoặc lỗi bị bỏ)"
        return good

    async def _prepare_file(self) -> None:
        item = self.item
        fresh = not item.segments or not os.path.exists(item.part_path)
        if fresh:
            item.segments = []
        if item.size > 0 and fresh:
            os.makedirs(item.save_dir, exist_ok=True)
            free = shutil.disk_usage(item.save_dir).free
            if free < item.size:
                raise DownloadError(f"Không đủ dung lượng ổ đĩa: cần {fmt_size(item.size)}, còn {fmt_size(free)}")
        multi = self.ranged and item.size > 0
        await self.loop.run_in_executor(
            self.engine.io_pool, self.part.open, item.size if multi else 0, fresh or not multi)
        if multi:
            self.segmap = (SegmentMap.from_saved(item.size, item.segments) if item.segments
                           else SegmentMap(item.size))
            self.received_total = self._last_bytes = self.segmap.received()

    # ================= chế độ đa kết nối =================
    async def _run_multi(self) -> None:
        item = self.item
        self.max_conn = max(1, min(32, item.connections or self.settings.max_connections))
        remembered = self.engine.host_caps.get(host_of(self.urls[0]))
        self.conn_cap = max(1, min(self.max_conn, remembered or self.max_conn))
        self.min_split = max(256 * 1024, self.settings.min_split_kb * 1024)
        last_ckpt = time.monotonic()
        self._spawn()
        while not (self._fatal or self._stop or self._switch_single):
            if self.segmap.complete():
                break
            t = time.monotonic()
            if not self.workers:
                if not self._spawn():
                    break
            elif (len(self.workers) < self.conn_cap and t - self._last_spawn >= SPAWN_INTERVAL
                  and t >= self._backoff_until and self.engine.connection_budget() > 0):
                self._spawn()
            self._tick(t)
            if t - last_ckpt >= CHECKPOINT_EVERY:
                await self._checkpoint()
                last_ckpt = time.monotonic()
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), 0.1 if len(self.workers) < self.conn_cap else 0.25)
            except TimeoutError:
                pass
        await self._stop_workers()
        if not self._fatal and not self._switch_single and not self.segmap.complete() and not self._stop:
            self._fatal = DownloadError("Tất cả kết nối đều thất bại")

    def _split_threshold(self) -> int:
        """Ngưỡng chia đoạn động: đoạn nhỏ cỡ ~1,5 giây tải của 1 kết nối thì không chia nữa.

        Kết nối nhanh → giữ ngưỡng lớn (ít yêu cầu); kết nối chậm → cho chia nhỏ hơn để
        phần "đuôi" tệp không bị dồn cho một kết nối.
        """
        speeds = sorted(w.speed for w in self.workers.values() if w.speed > 0)
        if not speeds:
            return self.min_split
        median = speeds[len(speeds) // 2]
        return int(max(TAIL_MIN_SPLIT, min(self.min_split, median * 1.5)))

    def _spawn(self) -> bool:
        seg = self.segmap.take_unowned() or self.segmap.split_largest(self._split_threshold())
        if seg is None:
            return False
        wid = self._next_wid
        self._next_wid += 1
        w = WorkerInfo(wid, self.urls[(wid - 1) % len(self.urls)])
        w.seg = seg
        seg.worker = wid
        self.workers[wid] = w
        w.task = asyncio.create_task(self._worker(w), name=f"tdl-{self.item.id}-w{wid}")
        self._last_spawn = time.monotonic()
        return True

    def _next_segment(self, w: WorkerInfo) -> Segment | None:
        seg = self.segmap.take_unowned() or self.segmap.split_largest(self._split_threshold())
        if seg is not None:
            seg.worker = w.wid
        w.seg = seg
        return seg

    @staticmethod
    def _release(seg: Segment | None) -> None:
        if seg is not None:
            seg.worker = None
            seg.req_end = 0

    def _window(self, w: WorkerInfo) -> int:
        win = w.speed * WINDOW_SECONDS if w.speed > 0 else INITIAL_WINDOW
        return int(min(MAX_WINDOW, max(MIN_WINDOW, win)))

    def _reduce_cap(self, reason: str) -> None:
        new_cap = max(1, len(self.workers) - 1)
        if new_cap < self.conn_cap:
            self.conn_cap = new_cap
            self.engine.host_caps[host_of(self.urls[0])] = new_cap
            self.message = f"{reason} → giảm còn {new_cap} kết nối"
            log.info("%s: %s", self.item.filename, self.message)
        self._last_cap_cut = time.monotonic()
        self._backoff_until = time.monotonic() + 8.0

    async def _worker(self, w: WorkerInfo) -> None:
        seg = w.seg
        try:
            while not self.halted:
                if seg is None or seg.done:
                    self._release(seg)
                    seg = self._next_segment(w)
                    if seg is None:
                        return
                try:
                    got = await self._fetch(w, seg)
                    if got:
                        w.failures = 0
                except ThrottledError as e:
                    if len(self.workers) > 1:
                        self._reduce_cap(f"Máy chủ giới hạn (HTTP {e.status})")
                        return
                    w.failures += 1
                    w.state = f"Máy chủ bận, chờ {e.retry_after or 2 ** w.failures:.0f} giây…"
                    if w.failures > self.settings.max_retries:
                        self._fatal = e
                        return
                    await self._sleep(e.retry_after or min(60.0, 2.0 ** w.failures))
                except RangeIgnoredError:
                    self._switch_single = True
                    self._wake.set()
                    return
                except ResourceChangedError as e:
                    self._fatal = e
                    return
                except TransientError as e:
                    if not await self._retry_or_quit(w, e):
                        return
                except DownloadError as e:
                    # 403/404… trên kết nối phụ khi kết nối khác vẫn chạy: thường là giới hạn số kết nối
                    if len(self.workers) > 1 and e.status in (401, 403, 404, 410):
                        self._reduce_cap(f"Kết nối phụ bị từ chối (HTTP {e.status})")
                        return
                    self._fatal = e
                    return
                except NET_ERRORS as e:
                    if isinstance(e, httpx.ConnectError) and len(self.workers) > 1 and w.total == 0:
                        self._reduce_cap("Máy chủ từ chối thêm kết nối")
                        return
                    if not await self._retry_or_quit(w, e):
                        return
        finally:
            self._release(seg)
            self.workers.pop(w.wid, None)
            self._wake.set()

    async def _retry_or_quit(self, w: WorkerInfo, e: BaseException) -> bool:
        w.failures += 1
        if w.failures > self.settings.max_retries:
            if len(self.workers) <= 1:
                self._fatal = DownloadError(f"Mất kết nối sau {w.failures - 1} lần thử: {_short(e)}")
            return False
        delay = min(30.0, 2.0 ** (w.failures - 1)) * random.uniform(0.8, 1.2)
        w.state = f"Lỗi: {_short(e)} — thử lại sau {delay:.0f} giây (lần {w.failures})"
        await self._sleep(delay)
        return True

    async def _fetch(self, w: WorkerInfo, seg: Segment) -> int:
        start = seg.pos
        req_end = min(seg.end, start + self._window(w))
        seg.req_end = req_end
        headers = {"Range": f"bytes={start}-{req_end - 1}", "Accept-Encoding": "identity"}
        if self.validator:
            headers["If-Range"] = self.validator
        w.state = "Đang gửi yêu cầu…"
        got = 0
        async with self.client.stream("GET", w.url, headers=headers) as r:
            st = r.status_code
            if st == 206:
                cr = parse_content_range(r.headers.get("content-range", ""))
                if not cr or cr[0] != start:
                    raise TransientError("Phản hồi Range không khớp vị trí yêu cầu")
                if cr[2] >= 0 and cr[2] != self.item.size:
                    raise ResourceChangedError("Kích thước tệp trên máy chủ đã thay đổi — hãy tải lại từ đầu")
                resp_end = cr[1] + 1
            elif st == 200:
                if self.validator and "If-Range" in headers:
                    raise ResourceChangedError("Tệp trên máy chủ đã thay đổi (If-Range) — hãy tải lại từ đầu")
                raise RangeIgnoredError("Máy chủ bỏ qua yêu cầu Range")
            elif st == 416:
                raise ResourceChangedError("Máy chủ từ chối vùng dữ liệu (HTTP 416) — tệp có thể đã thay đổi")
            else:
                raise http_error(st, r.headers.get("retry-after"))
            seg.req_end = min(resp_end, seg.end)
            w.state = "Đang nhận dữ liệu…"
            buf = bytearray()
            try:
                async for chunk in r.aiter_raw(self._read_size()):
                    n = len(chunk)
                    if self.limiter.rate > 0:
                        await self.limiter.consume(n)
                    if self.engine.limiter.rate > 0:
                        await self.engine.limiter.consume(n)
                    if self.halted:
                        break
                    room = min(seg.end, resp_end) - seg.pos
                    if room <= 0:
                        break
                    if n > room:
                        chunk = chunk[:room]
                        n = room
                    buf += chunk
                    seg.pos += n
                    got += n
                    w.bytes_tick += n
                    w.total += n
                    self.received_total += n
                    if len(buf) >= FLUSH_SIZE:
                        await self._flush(seg, buf)
                    if seg.pos >= seg.end and seg.end < resp_end:
                        break  # đoạn đã bị chia cho kết nối khác: bỏ phần còn lại của phản hồi
            finally:
                if buf:
                    await self._flush(seg, buf)
            if not self.halted and seg.pos < min(seg.end, resp_end):
                raise TransientError("Kết nối bị đóng giữa chừng")
        return got

    def _read_size(self) -> int:
        size = READ_CHUNK
        if self.limiter.rate > 0:
            size = self.limiter.read_size(size)
        if self.engine.limiter.rate > 0:
            size = self.engine.limiter.read_size(size)
        return size

    async def _flush(self, seg: Segment, buf: bytearray) -> None:
        data = bytes(buf)
        buf.clear()
        off = seg.written
        await self.loop.run_in_executor(self.engine.io_pool, self.part.write_at, off, data)
        seg.written = off + len(data)

    # ================= chế độ 1 kết nối =================
    async def _run_single(self) -> None:
        """Máy chủ không hỗ trợ Range / không rõ kích thước: 1 kết nối, đứt thì tải lại từ đầu."""
        item = self.item
        w = WorkerInfo(1, self.urls[0] if self.urls else item.url)
        self.workers = {1: w}
        attempt = 0
        try:
            while not self._stop:
                seg = Segment(0, max(item.size, 0), 0, 0, worker=1)
                self.single_seg = seg
                self.received_total = self._last_bytes = 0
                try:
                    await self._single_attempt(w, seg)
                    return
                except TransientError as e:
                    err: BaseException = e
                except NET_ERRORS as e:
                    err = e
                attempt += 1
                if attempt > self.settings.max_retries or self._stop:
                    raise DownloadError(f"Mất kết nối và máy chủ không hỗ trợ tải tiếp: {_short(err)}")
                self.message = f"Mất kết nối ({_short(err)}) — máy chủ không hỗ trợ tải tiếp, tải lại từ đầu…"
                w.state = self.message
                await self._sleep(min(30.0, 2.0 ** (attempt - 1)))
                await self.loop.run_in_executor(self.engine.io_pool, self.part.truncate, 0)
        finally:
            self.workers.pop(1, None)

    async def _single_attempt(self, w: WorkerInfo, seg: Segment) -> None:
        item = self.item
        tick_task = asyncio.create_task(self._single_ticker())
        try:
            async with self.client.stream("GET", w.url, headers={"Accept-Encoding": "identity"}) as r:
                if r.status_code != 200:
                    raise http_error(r.status_code, r.headers.get("retry-after"))
                w.state = "Đang nhận dữ liệu…"
                buf = bytearray()
                try:
                    async for chunk in r.aiter_raw(self._read_size()):
                        n = len(chunk)
                        if self.limiter.rate > 0:
                            await self.limiter.consume(n)
                        if self.engine.limiter.rate > 0:
                            await self.engine.limiter.consume(n)
                        if self._stop:
                            return
                        buf += chunk
                        seg.pos += n
                        if seg.pos > seg.end:
                            seg.end = seg.pos
                        w.bytes_tick += n
                        w.total += n
                        self.received_total += n
                        if len(buf) >= FLUSH_SIZE:
                            await self._flush(seg, buf)
                finally:
                    if buf:
                        await self._flush(seg, buf)
            if item.size >= 0 and seg.pos < item.size:
                raise TransientError("Kết nối bị đóng giữa chừng")
            if item.size < 0:
                item.size = seg.pos
        finally:
            tick_task.cancel()

    async def _single_ticker(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            self._tick(time.monotonic())

    # ================= thống kê & lưu =================
    def _tick(self, t: float) -> None:
        dt = t - self._last_tick
        if dt < 0.45:
            return
        inst = (self.received_total - self._last_bytes) / dt
        self.speed = inst if self.speed == 0 else self.speed * 0.6 + inst * 0.4
        self._last_bytes = self.received_total
        self._last_tick = t
        for w in self.workers.values():
            ws = w.bytes_tick / dt
            w.speed = ws if w.speed == 0 else w.speed * 0.6 + ws * 0.4
            w.bytes_tick = 0
        if self.segmap is not None and self.ranged:
            self.item.downloaded = self.segmap.received()
        elif self.single_seg is not None:
            self.item.downloaded = self.single_seg.pos
        # AIMD: sau một thời gian yên ổn thì thử tăng lại số kết nối
        if self.conn_cap < self.max_conn and self._last_cap_cut and t - self._last_cap_cut > CAP_RECOVER_AFTER:
            self.conn_cap += 1
            self._last_cap_cut = t

    async def _checkpoint(self) -> None:
        if self.segmap is None:
            return
        saved = self.segmap.to_saved()           # chụp vị trí TRƯỚC khi fsync
        await self.loop.run_in_executor(self.engine.io_pool, self.part.sync)
        self.item.segments = saved
        self.engine.persist(self.item)

    async def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while not self.halted and time.monotonic() < end:
            await asyncio.sleep(min(0.25, end - time.monotonic()))

    async def _stop_workers(self) -> None:
        tasks = [w.task for w in list(self.workers.values()) if w.task and not w.task.done()]
        if not tasks:
            return
        done, pending = await asyncio.wait(tasks, timeout=1.0)
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    # ================= kết thúc =================
    async def _finish_stopped(self) -> None:
        item = self.item
        if self.segmap is not None and self.ranged:
            item.segments = self.segmap.to_saved()
            item.downloaded = self.segmap.written()
        elif self._probed and not self.ranged:
            item.segments = []
            item.downloaded = 0
        item.status = M.QUEUED if self.engine.requeue_on_stop(item) else M.PAUSED
        self.engine.changed(item, persist=True)

    async def _finish_error(self, msg: str) -> None:
        item = self.item
        if self.segmap is not None and self.ranged:
            item.segments = self.segmap.to_saved()
            item.downloaded = self.segmap.written()
        item.status = M.ERROR
        item.error = msg
        log.warning("%s: %s", item.filename, msg)
        self.engine.changed(item, persist=True)
        self.engine.emit("error", item)

    async def _finalize(self) -> None:
        item = self.item
        await self.loop.run_in_executor(self.engine.io_pool, self.part.close, True)
        final_name = item.filename
        if os.path.exists(item.path):
            final_name = unique_path(item.save_dir, item.filename)
        os.replace(item.part_path, os.path.join(item.save_dir, final_name))
        item.filename = final_name
        mark_of_the_web(item.path, item.url, item.page_url or item.referer)
        item.segments = []
        item.downloaded = item.size if item.size >= 0 else item.downloaded
        if not item.checksum and self.settings.auto_checksum_sidecar and item.size > 1024 * 1024:
            item.checksum = await self._find_sidecar_checksum()
        if item.checksum:
            item.status = M.VERIFYING
            self.engine.changed(item)
            item.checksum_ok = await self.loop.run_in_executor(None, verify_checksum, item.path, item.checksum)
            if item.checksum_ok is False:
                self.message = "Sai checksum — tệp có thể bị hỏng hoặc bị thay đổi"
        item.status = M.COMPLETED
        item.completed = now()
        item.error = "" if item.checksum_ok is not False else self.message
        self.engine.changed(item, persist=True)
        self.engine.emit("completed", item)

    async def _find_sidecar_checksum(self) -> str:
        """Nhiều nơi (GitHub release, ảnh ISO…) để sẵn <tệp>.sha256 cạnh link — tự lấy về để kiểm tra."""
        base = self.item.url.split("?", 1)[0].split("#", 1)[0]
        name = os.path.basename(base)
        for suffix in (".sha256", ".sha256sum"):
            try:
                r = await self.client.get(base + suffix, timeout=5.0)
            except Exception:
                continue
            if r.status_code != 200 or len(r.content) > 8192:
                continue
            text = r.text
            for line in text.splitlines():
                m = re.match(r"\s*([0-9a-fA-F]{64})\b\s*\*?(.*)$", line)
                if m and (not m.group(2).strip() or m.group(2).strip().lstrip("*") == name):
                    return "sha256:" + m.group(1).lower()
        return ""


def verify_checksum(path: str, spec: str) -> bool | None:
    try:
        algo, expected = spec.split(":", 1)
        h = hashlib.new(algo.strip().lower())
    except (ValueError, TypeError):
        return None
    with open(path, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower() == expected.strip().lower()

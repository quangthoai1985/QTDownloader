"""API HTTP tối giản trên 127.0.0.1 để extension trình duyệt chuyển link sang.

Native Messaging cần ghi registry + một exe host riêng. QT Downloader dùng HTTP localhost cho
đơn giản, kèm các lớp bảo vệ:
  * chỉ nghe 127.0.0.1;
  * Host phải là 127.0.0.1/localhost:<cổng> (chống DNS rebinding);
  * Origin chỉ chấp nhận chrome-extension:// · moz-extension:// (hoặc không có Origin — CLI/script);
  * POST bắt buộc Content-Type: application/json → trang web lạ luôn phải qua preflight CORS,
    mà preflight chỉ được duyệt cho Origin của extension.
"""

from __future__ import annotations

import asyncio
import json
import logging

from .. import __version__

log = logging.getLogger("qtdownloader.api")

MAX_BODY = 4 * 1024 * 1024
EXT_ORIGINS = ("chrome-extension://", "moz-extension://", "extension://", "safari-web-extension://")


class LocalApiServer:
    def __init__(self, engine, port: int):
        self.engine = engine
        self.port = port
        self.server: asyncio.base_events.Server | None = None

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", self.port)

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    # ------------------------------------------------------------------ HTTP
    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
            lines = head.decode("latin-1").split("\r\n")
            method, path, _ = lines[0].split(" ", 2)
            headers = {}
            for ln in lines[1:]:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
            length = int(headers.get("content-length", "0") or 0)
            if length > MAX_BODY:
                return await self._send(writer, 413, {"error": "body too large"})
            body = await asyncio.wait_for(reader.readexactly(length), 10) if length else b""
            await self._route(writer, method.upper(), path.split("?", 1)[0], headers, body)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError, ValueError,
                ConnectionError):
            pass
        except Exception:
            log.exception("Lỗi API")
            try:
                await self._send(writer, 500, {"error": "internal"})
            except Exception:
                pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    def _origin_ok(self, origin: str | None) -> bool:
        return origin is None or origin.startswith(EXT_ORIGINS)

    def _host_ok(self, host: str) -> bool:
        return host in (f"127.0.0.1:{self.port}", f"localhost:{self.port}", "127.0.0.1", "localhost")

    async def _route(self, w, method: str, path: str, h: dict, body: bytes) -> None:
        origin = h.get("origin")
        if not self._host_ok(h.get("host", "")) or not self._origin_ok(origin):
            return await self._send(w, 403, {"error": "forbidden"})
        cors = {}
        if origin:
            cors = {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Private-Network": "true",
                "Vary": "Origin",
            }
        if method == "OPTIONS":
            return await self._send(w, 204, None, cors)
        if method == "GET" and path == "/api/ping":
            snap = self.engine.snapshot
            # protocol: extension nhớ để biết có nên thử mở app qua qtdownloader:// khi app tắt hay không
            return await self._send(w, 200, {"app": "QT Downloader", "version": __version__,
                                             "active": snap.get("active", 0),
                                             "protocol": bool(self.engine.settings.browser_protocol)}, cors)
        if method != "POST":
            return await self._send(w, 404, {"error": "not found"}, cors)
        if not h.get("content-type", "").lower().startswith("application/json"):
            return await self._send(w, 415, {"error": "json required"}, cors)
        try:
            data = json.loads(body.decode("utf-8") or "{}")
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            return await self._send(w, 400, {"error": "bad json"}, cors)
        if path == "/api/add":
            if not str(data.get("url", "")).lower().startswith(("http://", "https://")):
                return await self._send(w, 400, {"error": "bad url"}, cors)
            await self.engine.handle_browser_add(data)
            return await self._send(w, 200, {"ok": True}, cors)
        if path == "/api/add-batch":
            items = [i for i in data.get("items", []) if isinstance(i, dict)
                     and str(i.get("url", "")).lower().startswith(("http://", "https://"))]
            if not items:
                return await self._send(w, 400, {"error": "no items"}, cors)
            data["items"] = items[:5000]
            data["batch"] = True
            await self.engine.handle_browser_add(data)
            return await self._send(w, 200, {"ok": True, "count": len(data["items"])}, cors)
        return await self._send(w, 404, {"error": "not found"}, cors)

    @staticmethod
    async def _send(w, status: int, payload, extra: dict | None = None) -> None:
        reason = {200: "OK", 204: "No Content", 400: "Bad Request", 403: "Forbidden", 404: "Not Found",
                  413: "Payload Too Large", 415: "Unsupported Media Type", 500: "Internal Server Error"}
        body = b"" if payload is None else json.dumps(payload).encode()
        hdr = [f"HTTP/1.1 {status} {reason.get(status, 'OK')}", "Connection: close",
               f"Content-Length: {len(body)}"]
        if payload is not None:
            hdr.append("Content-Type: application/json")
        for k, v in (extra or {}).items():
            hdr.append(f"{k}: {v}")
        w.write(("\r\n".join(hdr) + "\r\n\r\n").encode("latin-1") + body)
        await w.drain()

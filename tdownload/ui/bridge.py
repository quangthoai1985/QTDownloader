"""Cầu nối luồng engine (asyncio) ↔ luồng giao diện Qt."""

from __future__ import annotations

import logging
import os
import subprocess
import sys

from PySide6.QtCore import QObject, Signal

from ..core.models import DownloadItem

log = logging.getLogger("tdownload.ui")


class Bridge(QObject):
    event = Signal(str, object)
    _done = Signal(object, object, object)

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._done.connect(self._dispatch)
        engine.listeners.append(self._on_engine_event)

    def _on_engine_event(self, kind: str, payload) -> None:  # chạy trong luồng engine
        if isinstance(payload, DownloadItem):
            payload = payload.to_dict()
        self.event.emit(kind, payload)

    def run(self, fn, *args, on_done=None, **kwargs):
        fut = self.engine.call(fn, *args, **kwargs)

        def cb(f):
            try:
                res, err = f.result(), None
            except BaseException as e:  # noqa: BLE001 — chuyển lỗi về UI
                res, err = None, e
            if on_done is not None:
                self._done.emit(on_done, res, err)
            elif err is not None:
                log.error("Lỗi khi gọi %s: %s", getattr(fn, "__name__", fn), err)

        fut.add_done_callback(cb)
        return fut

    @staticmethod
    def _dispatch(cb, res, err):
        cb(res, err)

    @property
    def settings(self):
        return self.engine.settings

    def item(self, ident: str) -> dict | None:
        return self.engine.snapshot["items"].get(ident)


def open_path(path: str) -> None:
    if not os.path.exists(path):
        return
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", path])


def reveal_path(path: str) -> None:
    if sys.platform == "win32":
        if os.path.exists(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            folder = os.path.dirname(path)
            if os.path.isdir(folder):
                os.startfile(folder)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])

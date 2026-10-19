import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server as test_server  # noqa: E402
from tdownload.core.engine import Engine  # noqa: E402


@pytest.fixture(scope="session")
def srv():
    s, base = test_server.start(0)
    yield base
    s.shutdown()


@pytest.fixture
def engine(tmp_path):
    eng = Engine(tmp_path / "data", start_api=False)
    eng.start()
    eng.call_sync(eng.update_settings, {"download_dir": str(tmp_path / "dl"), "auto_checksum_sidecar": False})
    yield eng
    eng.shutdown()


def wait_done(eng, ident, timeout=60.0, statuses=("completed", "error")):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        s = eng.snapshot["items"].get(ident)
        if s and s["status"] in statuses:
            return s
        time.sleep(0.1)
    raise AssertionError(f"Hết giờ chờ, trạng thái: {eng.snapshot['items'].get(ident)}")


def wait_until(pred, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError("Hết giờ chờ điều kiện")

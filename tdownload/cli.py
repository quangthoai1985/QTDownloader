"""Dùng TDownload không cần giao diện.

    python -m tdownload.cli URL [URL…] [-c 8] [-o THƯ_MỤC] [-l 500] [--mirror URL2]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time

from .core import models as M
from .core.engine import Engine
from .core.util import fmt_eta, fmt_size, fmt_speed


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(prog="tdownload", description="Trình tải đa kết nối TDownload (CLI)")
    p.add_argument("urls", nargs="+", help="địa chỉ http(s) hoặc .m3u8")
    p.add_argument("-o", "--output-dir", default="", help="thư mục lưu (mặc định theo cài đặt)")
    p.add_argument("-c", "--connections", type=int, default=0, help="số kết nối / tệp (1–32)")
    p.add_argument("-l", "--limit", type=int, default=0, help="giới hạn tốc độ toàn cục, KB/s")
    p.add_argument("--mirror", action="append", default=[], help="nguồn phụ cùng tệp (dùng nhiều lần)")
    p.add_argument("--checksum", default="", help="vd sha256:abcd…")
    p.add_argument("--data-dir", default="", help="thư mục dữ liệu engine (mặc định: thư mục tạm)")
    args = p.parse_args(argv)

    eng = Engine(args.data_dir or tempfile.mkdtemp(prefix="tdl-cli-"), start_api=False)
    eng.start()
    if args.limit:
        eng.call_sync(eng.update_settings, {"global_speed_limit_kb": args.limit})
    ids = [eng.call_sync(eng.add, u, save_dir=args.output_dir, connections=args.connections,
                         mirrors=args.mirror, checksum=args.checksum) for u in args.urls]
    t0 = time.monotonic()
    try:
        while True:
            time.sleep(0.5)
            snap = eng.snapshot["items"]
            parts = []
            for i in ids:
                s = snap.get(i)
                if not s:
                    continue
                pct = f"{s['progress'] * 100:5.1f}%" if s["progress"] is not None else "  ?  "
                parts.append(f"{s['filename'][:28]:28} {pct} {fmt_size(s['downloaded']):>10} "
                             f"{fmt_speed(s['speed']):>12} {len(s['conns']):2}k {fmt_eta(s['eta'])}")
            sys.stdout.write("\r" + " | ".join(parts)[:200].ljust(120))
            sys.stdout.flush()
            if all(snap.get(i, {}).get("status") in (M.COMPLETED, M.ERROR) for i in ids):
                break
    except KeyboardInterrupt:
        print("\nĐang dừng và lưu trạng thái…")
    finally:
        snap = eng.snapshot["items"]
        eng.shutdown()
    print()
    rc = 0
    for i in ids:
        s = snap.get(i, {})
        if s.get("status") == M.COMPLETED:
            chk = {True: " · checksum OK", False: " · SAI CHECKSUM"}.get(s.get("checksum_ok"), "")
            print(f"✔ {s['path']}  ({fmt_size(s['size'])}, {time.monotonic() - t0:.1f}s){chk}")
            rc |= 1 if s.get("checksum_ok") is False else 0
        else:
            print(f"✘ {s.get('filename', '?')}: {s.get('error') or s.get('status_text')}")
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

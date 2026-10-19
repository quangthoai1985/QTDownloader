"""Lưu danh sách tải vào SQLite (WAL) để resume sau khi tắt app/mất điện."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class Storage:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS downloads(id TEXT PRIMARY KEY, created REAL, data TEXT NOT NULL)")

    def load_all(self) -> list[dict]:
        rows = self.db.execute("SELECT data FROM downloads ORDER BY created").fetchall()
        out = []
        for (data,) in rows:
            try:
                out.append(json.loads(data))
            except ValueError:
                continue
        return out

    def save(self, d: dict) -> None:
        self.db.execute(
            "INSERT INTO downloads(id, created, data) VALUES(?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
            (d["id"], d.get("created", 0), json.dumps(d, ensure_ascii=False)),
        )

    def delete(self, ident: str) -> None:
        self.db.execute("DELETE FROM downloads WHERE id = ?", (ident,))

    def close(self) -> None:
        self.db.close()

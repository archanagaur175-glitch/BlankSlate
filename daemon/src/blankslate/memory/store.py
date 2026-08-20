"""Local SQLite history store with redaction at the write boundary."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from blankslate.security.redactor import Redactor


class HistoryStore:
    def __init__(self, db_path: Path | str, redactor: Redactor | None = None) -> None:
        self.db_path = Path(db_path)
        self.redactor = redactor or Redactor(enabled=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'voice'
            )
            """
        )
        self._conn.commit()

    def append(self, role: str, content: str, source: str = "voice") -> None:
        safe = self.redactor.redact(content)
        self._conn.execute(
            "INSERT INTO turns (ts, role, content, source) VALUES (?, ?, ?, ?)",
            (time.time(), role, safe, source),
        )
        self._conn.commit()

    def recent(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT ts, role, content, source FROM turns ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"ts": ts, "role": role, "content": content, "source": source}
            for ts, role, content, source in reversed(rows)
        ]

    def clear(self) -> None:
        self._conn.execute("DELETE FROM turns")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @property
    def redaction_enabled(self) -> bool:
        return self.redactor.enabled
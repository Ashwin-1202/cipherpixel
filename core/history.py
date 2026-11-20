"""Operation history (SQLite).

Privacy: stores only metadata – file name, type, operation, timestamp, size, status.
It never stores passwords, keys, plaintext image bytes, salts or nonces.
Aggregate counters are kept in a separate table so dashboard totals survive even when
detailed history recording is switched off or the history is cleared.
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass

ENCRYPT = "encrypt"
DECRYPT = "decrypt"
SUCCESS = "success"
FAILED = "failed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT    NOT NULL,
    operation TEXT    NOT NULL CHECK (operation IN ('encrypt','decrypt')),
    file_name TEXT    NOT NULL,
    file_type TEXT    NOT NULL,
    file_size INTEGER NOT NULL,
    status    TEXT    NOT NULL CHECK (status IN ('success','failed'))
);
CREATE INDEX IF NOT EXISTS idx_history_ts ON history(ts);
CREATE TABLE IF NOT EXISTS counters (
    name  TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    ts: str  # ISO-8601, UTC
    operation: str
    file_name: str
    file_type: str
    file_size: int
    status: str

    @property
    def local_time(self) -> dt.datetime:
        return dt.datetime.fromisoformat(self.ts).astimezone()


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class HistoryStore:
    def __init__(self, path: str | os.PathLike) -> None:
        self.path = str(path)
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with closing(self._connect()) as db, db:
            db.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    # ---- writing ------------------------------------------------------------
    def record(
        self,
        operation: str,
        file_name: str,
        file_type: str,
        file_size: int,
        status: str,
        *,
        store_entry: bool = True,
    ) -> None:
        """Record an operation.  Counters always update on success; the row only if ``store_entry``."""
        with closing(self._connect()) as db, db:
            if store_entry:
                db.execute(
                    "INSERT INTO history (ts, operation, file_name, file_type, file_size, status) "
                    "VALUES (?,?,?,?,?,?)",
                    (dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                     operation, file_name, file_type.upper(), int(file_size), status),
                )
            if status == SUCCESS:
                db.execute(
                    "INSERT INTO counters(name, value) VALUES (?, 1) "
                    "ON CONFLICT(name) DO UPDATE SET value = value + 1",
                    (operation,),
                )

    def clear(self) -> None:
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM history")

    def delete(self, ids: list[int]) -> None:
        if not ids:
            return
        with closing(self._connect()) as db, db:
            db.executemany("DELETE FROM history WHERE id = ?", [(int(i),) for i in ids])

    # ---- reading ------------------------------------------------------------
    def list(self, *, search: str = "", operation: str | None = None,
             newest_first: bool = True, limit: int | None = None) -> list[HistoryEntry]:
        sql = "SELECT * FROM history WHERE 1=1"
        params: list = []
        if operation in (ENCRYPT, DECRYPT):
            sql += " AND operation = ?"
            params.append(operation)
        if search.strip():
            sql += " AND file_name LIKE ? ESCAPE '\\'"
            params.append(f"%{_escape_like(search.strip())}%")
        sql += " ORDER BY ts {0}, id {0}".format("DESC" if newest_first else "ASC")
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        with closing(self._connect()) as db:
            return [HistoryEntry(**dict(r)) for r in db.execute(sql, params)]

    def counts(self) -> dict[str, int]:
        with closing(self._connect()) as db:
            rows = {r["name"]: r["value"] for r in db.execute("SELECT name, value FROM counters")}
        enc, dec = rows.get(ENCRYPT, 0), rows.get(DECRYPT, 0)
        return {"encrypted": enc, "decrypted": dec, "processed": enc + dec}

    def export_csv(self, dest: str, entries: list[HistoryEntry] | None = None) -> int:
        entries = self.list() if entries is None else entries
        with open(dest, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Date/Time (local)", "Operation", "File name", "File type", "Size (bytes)", "Status"])
            for e in entries:
                writer.writerow([e.local_time.strftime("%Y-%m-%d %H:%M:%S"), e.operation, _csv_safe(e.file_name),
                                 e.file_type, e.file_size, e.status])
        return len(entries)


def _csv_safe(value: str) -> str:
    """Neutralise spreadsheet formula injection from attacker-controlled file names."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value

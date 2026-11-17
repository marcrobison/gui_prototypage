"""SQLite-backed security event log (capped at config.LOG_CAP rows) and persisted settings. Thread-safe."""
import csv
import datetime
import io
import sqlite3
import threading
import time
from pathlib import Path

from . import config

SEVERITIES = ("HIGH", "MEDIUM", "INFO")


def format_ts(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


class EventLog:
    def __init__(self, path: Path | str = config.DB_PATH, cap: int = config.LOG_CAP):
        self.cap = cap
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts         REAL    NOT NULL,
                    event_type TEXT    NOT NULL,
                    details    TEXT    NOT NULL,
                    severity   TEXT    NOT NULL
                )""")
            # Small key/value store so state such as "armed" survives a reboot.
            self._db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    @staticmethod
    def _to_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "ts": row["ts"],
            "timestamp": format_ts(row["ts"]),
            "event_type": row["event_type"],
            "details": row["details"],
            "severity": row["severity"],
        }

    def add(self, event_type: str, details: str, severity: str = "INFO", ts: float | None = None) -> dict:
        if severity not in SEVERITIES:
            raise ValueError(f"unknown severity {severity!r}")
        ts = time.time() if ts is None else ts
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO events (ts, event_type, details, severity) VALUES (?, ?, ?, ?)",
                (ts, event_type, details, severity))
            new_id = cur.lastrowid
            self._db.execute(
                "DELETE FROM events WHERE id <= (SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET ?)",
                (self.cap,))
            row = self._db.execute("SELECT * FROM events WHERE id = ?", (new_id,)).fetchone()
        return self._to_dict(row)

    def recent(self, limit: int = config.LOG_TABLE_ROWS, severity: str | None = None) -> list[dict]:
        limit = max(1, min(int(limit), self.cap))
        with self._lock:
            if severity:
                rows = self._db.execute(
                    "SELECT * FROM events WHERE severity = ? ORDER BY id DESC LIMIT ?", (severity, limit))
            else:
                rows = self._db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
            return [self._to_dict(r) for r in rows.fetchall()]

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def to_csv(self) -> str:
        with self._lock:
            rows = self._db.execute("SELECT * FROM events ORDER BY id ASC").fetchall()
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["id", "timestamp", "event_type", "details", "severity"])
        for r in rows:
            writer.writerow([r["id"], format_ts(r["ts"]), r["event_type"], r["details"], r["severity"]])
        return out.getvalue()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._lock, self._db:
            self._db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                             "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def close(self):
        with self._lock:
            self._db.close()

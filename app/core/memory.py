"""SQLite storage: short dialogue history per user and the list of bookings."""
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_user ON history (channel, user_id, id);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    channel TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    service TEXT NOT NULL,
    slot TEXT NOT NULL,
    contact TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new'
);
CREATE INDEX IF NOT EXISTS idx_bookings_slot ON bookings (slot);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Memory:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._db.commit()

    # --- history ---------------------------------------------------------
    def add(self, channel: str, user_id: str | int, role: str, content: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO history (channel, user_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (channel, str(user_id), role, content, _utc_now()),
            )
            self._db.commit()

    def history(self, channel: str, user_id: str | int, limit: int = 12) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT role, content FROM history WHERE channel = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
                (channel, str(user_id), limit),
            ).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    def reset(self, channel: str, user_id: str | int) -> None:
        with self._lock:
            self._db.execute("DELETE FROM history WHERE channel = ? AND user_id = ?", (channel, str(user_id)))
            self._db.commit()

    # --- bookings --------------------------------------------------------
    def slot_taken(self, slot: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM bookings WHERE slot = ? AND status != 'cancelled' LIMIT 1", (slot,)
            ).fetchone()
        return row is not None

    def has_booking(self, channel: str, user_id: str | int, slot: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM bookings WHERE channel = ? AND user_id = ? AND slot = ? AND status != 'cancelled' LIMIT 1",
                (channel, str(user_id), slot),
            ).fetchone()
        return row is not None

    def save_booking(self, channel: str, user_id: str | int, name: str, service: str, slot: str, contact: str) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO bookings (created_at, channel, user_id, name, service, slot, contact) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (_utc_now(), channel, str(user_id), name, service, slot, contact),
            )
            self._db.commit()
            return int(cur.lastrowid)

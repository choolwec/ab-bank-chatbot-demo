"""Which desk conversation belongs to which customer session (ticket H2).

One small SQLite table in data/desk.db, so an agent's reply (a webhook that
names only the Chatwoot conversation) finds its way back to the customer. It
holds the HASHED session key ("whatsapp:<hash>") and the ticket reference,
never a phone number or platform id. The file is created on first use: with
the desk off it never appears. Rows follow TRANSCRIPT_RETENTION_DAYS.
"""

import sqlite3
import threading
import time

from .. import config

FILE_NAME = "desk.db"


class Links:
    def __init__(self, path=None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._ready_for = None

    @property
    def path(self):
        # read at call time, so tests pointing DATA_DIR at a temp dir are respected
        return self._path or config.DATA_DIR / FILE_NAME

    def _connect(self):
        path = self.path
        con = sqlite3.connect(path, timeout=10)
        if self._ready_for != path:
            con.execute(
                """CREATE TABLE IF NOT EXISTS links (
                    conversation_id TEXT PRIMARY KEY,
                    session_key TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    ref TEXT,
                    created REAL NOT NULL
                )"""
            )
            self._ready_for = path
        return con

    def save(self, conversation_id, session_key: str, channel: str, ref: str | None) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO links (conversation_id, session_key, channel, ref, created)"
                " VALUES (?, ?, ?, ?, ?)",
                (str(conversation_id), session_key, channel, ref, time.time()),
            )

    def lookup(self, conversation_id) -> dict | None:
        if not self.path.exists():
            return None
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT session_key, channel, ref FROM links WHERE conversation_id = ?",
                (str(conversation_id),),
            ).fetchone()
        return {"session_key": row[0], "channel": row[1], "ref": row[2]} if row else None

    def purge(self, days: int) -> int:
        if not self.path.exists():
            return 0
        cutoff = time.time() - days * 86400
        with self._lock, self._connect() as con:
            return con.execute("DELETE FROM links WHERE created < ?", (cutoff,)).rowcount


links = Links()

"""Durable inbox for webhook channels (ticket W2, research §7.4).

The webhook writes each message here FIRST and only then returns 200, so an
acknowledged message is never lost; a single worker (worker.py) processes the
rows in arrival order, one at a time -- which also keeps each customer's
messages in order.

  id        "<channel>:<platform message id>" -- the PRIMARY KEY, so a duplicate
            delivery (Meta delivers at least once) is ignored for free
  message   the InboundMessage as JSON, with text ALREADY MASKED (guards run
            before storage, like everywhere else) and no raw user id
  findings  what guards.mask() found, so the PII warning is still shown
  user_ref  the raw platform user id, SEALED (identity.seal) -- needed to
            reply; cleared as soon as the row is processed
A row that keeps failing is retried up to MAX_ATTEMPTS, then marked failed;
a crash mid-row leaves it 'new', so it is picked up again after a restart.
"""

import dataclasses
import json
import sqlite3
import threading
import time

from . import config, guards
from .channels.base import InboundMessage
from .identity import seal, unseal, user_hash

MAX_ATTEMPTS = 5


class Inbox:
    def __init__(self, path=None) -> None:
        self.path = path or config.DATA_DIR / "inbox.db"
        self._db_lock = threading.Lock()
        self._process_lock = threading.Lock()
        with self._connect() as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS inbound (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    user_hash TEXT NOT NULL,
                    user_ref TEXT,
                    received REAL NOT NULL,
                    ts REAL,
                    message TEXT NOT NULL,
                    findings TEXT,
                    status TEXT NOT NULL DEFAULT 'new',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                )"""
            )
            con.execute("CREATE INDEX IF NOT EXISTS inbound_status ON inbound(status, received)")

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def store(self, msg: InboundMessage) -> bool:
        """Durably record one message. False if it was already seen."""
        masked, findings = guards.mask(guards.clean(msg.text)) if msg.text else ("", [])
        record = dataclasses.asdict(msg)
        record["text"] = masked if msg.text else None
        record["user_key"] = None  # only ever stored sealed, below
        record["phone_hint"] = seal(msg.phone_hint) if msg.phone_hint else None
        row_id = f"{msg.channel}:{msg.msg_id or f'{time.time_ns()}'}"
        with self._db_lock, self._connect() as con:
            cur = con.execute(
                "INSERT OR IGNORE INTO inbound (id, channel, user_hash, user_ref, received, ts, message, findings)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row_id, msg.channel, user_hash(msg.session_key), seal(msg.user_key),
                    time.time(), msg.ts, json.dumps(record, ensure_ascii=False), json.dumps(findings),
                ),
            )
            return cur.rowcount == 1

    def _pending(self):
        with self._db_lock, self._connect() as con:
            return con.execute(
                "SELECT id, user_ref, message, findings, attempts FROM inbound"
                " WHERE status = 'new' ORDER BY received, rowid"
            ).fetchall()

    def _finish(self, row_id, status, error=None, attempts=None):
        with self._db_lock, self._connect() as con:
            if status == "done":
                con.execute("UPDATE inbound SET status='done', user_ref=NULL, error=NULL WHERE id=?", (row_id,))
            elif status == "failed":
                con.execute("UPDATE inbound SET status='failed', user_ref=NULL, error=?, attempts=? WHERE id=?",
                            (error, attempts, row_id))
            else:
                con.execute("UPDATE inbound SET attempts=?, error=? WHERE id=?", (attempts, error, row_id))

    def process_pending(self, handler) -> int:
        """Run handler(msg, findings) for each new row, in arrival order.
        Serialised: two callers never process at the same time."""
        done = 0
        with self._process_lock:
            for row_id, user_ref, raw, findings, attempts in self._pending():
                record = json.loads(raw)
                record["user_key"] = unseal(user_ref) if user_ref else ""
                if record.get("phone_hint"):
                    record["phone_hint"] = unseal(record["phone_hint"])
                if isinstance(record.get("location"), list):
                    record["location"] = tuple(record["location"])
                msg = InboundMessage(**record)
                try:
                    handler(msg, json.loads(findings or "[]"))
                except Exception as exc:  # retried; never loses the row
                    attempts += 1
                    status = "failed" if attempts >= MAX_ATTEMPTS else "new"
                    self._finish(row_id, status, error=f"{type(exc).__name__}: {exc}"[:500], attempts=attempts)
                    continue
                self._finish(row_id, "done")
                done += 1
        return done

    def oldest_pending_age(self) -> float:
        """Seconds the oldest unprocessed message has waited (R1 alert)."""
        with self._db_lock, self._connect() as con:
            row = con.execute("SELECT MIN(received) FROM inbound WHERE status='new'").fetchone()
        return time.time() - row[0] if row and row[0] else 0.0

    def counts(self) -> dict:
        with self._db_lock, self._connect() as con:
            return dict(con.execute("SELECT status, COUNT(*) FROM inbound GROUP BY status").fetchall())

    def purge(self, days: int) -> int:
        cutoff = time.time() - days * 86400
        with self._db_lock, self._connect() as con:
            return con.execute("DELETE FROM inbound WHERE status != 'new' AND received < ?", (cutoff,)).rowcount


inbox = Inbox()

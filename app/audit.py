"""Structured audit trail (§3.3): SQLite + JSONL, written only AFTER masking.

Also owns tickets (fraud / complaint / callback) with the session transcript
attached, so a human never asks the customer to repeat themselves (§1 rule 7).
"""

import datetime as dt
import json
import secrets
import sqlite3
import string
import threading

from . import config

DB_FILE = config.DATA_DIR / "audit.db"
JSONL_FILE = config.DATA_DIR / "audit.jsonl"

_TICKET_PREFIX = {"fraud": "FRD", "complaint": "CMP", "callback": "CBK"}
_init_done = False
_lock = threading.Lock()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    init_db()
    return sqlite3.connect(DB_FILE)


def init_db() -> None:
    global _init_done
    if _init_done:
        return
    with _lock:
        if _init_done:
            return
        con = sqlite3.connect(DB_FILE)
        con.execute(
            """CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                text TEXT,
                intent TEXT,
                confidence REAL,
                action TEXT
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ref TEXT UNIQUE NOT NULL,
                type TEXT NOT NULL,
                created TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                fields TEXT,
                transcript TEXT
            )"""
        )
        con.commit()
        con.close()
        _init_done = True


def log_event(session_id, role, text, intent=None, confidence=None, action=None):
    row = {
        "ts": _now(),
        "session_id": session_id,
        "role": role,
        "text": text,
        "intent": intent,
        "confidence": confidence,
        "action": action,
    }
    con = _connect()
    con.execute(
        "INSERT INTO events (ts, session_id, role, text, intent, confidence, action)"
        " VALUES (:ts, :session_id, :role, :text, :intent, :confidence, :action)",
        row,
    )
    con.commit()
    con.close()
    with JSONL_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def create_ticket(kind: str, fields: dict, transcript: list) -> str:
    prefix = _TICKET_PREFIX.get(kind, "TKT")
    suffix = "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)
    )
    ref = f"{prefix}-{dt.date.today():%Y%m%d}-{suffix}"
    con = _connect()
    con.execute(
        "INSERT INTO tickets (ref, type, created, status, fields, transcript)"
        " VALUES (?, ?, ?, 'open', ?, ?)",
        (
            ref,
            kind,
            _now(),
            json.dumps(fields, ensure_ascii=False),
            json.dumps(transcript, ensure_ascii=False),
        ),
    )
    con.commit()
    con.close()
    log_event("-", "system", f"ticket created: {ref}", action=f"ticket:{kind}")
    return ref


def purge_expired() -> None:
    """Retention (§3.3) — periods configurable, to be confirmed by legal."""
    cutoff = (
        dt.datetime.now(dt.timezone.utc)
        - dt.timedelta(days=config.TRANSCRIPT_RETENTION_DAYS)
    ).isoformat(timespec="seconds")
    con = _connect()
    con.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
    if config.TICKET_RETENTION_DAYS > 0:
        tcut = (
            dt.datetime.now(dt.timezone.utc)
            - dt.timedelta(days=config.TICKET_RETENTION_DAYS)
        ).isoformat(timespec="seconds")
        con.execute("DELETE FROM tickets WHERE created < ?", (tcut,))
    con.commit()
    con.close()

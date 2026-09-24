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

from . import config, jira_export

DB_FILE = config.DATA_DIR / "audit.db"
JSONL_FILE = config.DATA_DIR / "audit.jsonl"

_TICKET_PREFIX = {"fraud": "FRD", "complaint": "CMP", "callback": "CBK", "handoff": "HND"}
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
        _migrate(con)
        con.commit()
        con.close()
        _init_done = True


# P6: columns added after launch. Each is (table, column, DDL); an existing
# database gets them with a default, so old rows read as channel "web".
_MIGRATIONS = [
    ("events", "channel", "TEXT NOT NULL DEFAULT 'web'"),
    ("events", "user_hash", "TEXT"),
    ("tickets", "channel", "TEXT NOT NULL DEFAULT 'web'"),
    ("tickets", "reply_to", "TEXT"),
]


def _migrate(con) -> None:
    for table, column, ddl in _MIGRATIONS:
        existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def log_event(session_id, role, text, intent=None, confidence=None, action=None,
              channel="web", user_hash=None):
    """`user_hash` is identity.user_hash(...) -- NEVER a raw phone number or
    platform id. Text is already masked by guards before it gets here."""
    row = {
        "ts": _now(),
        "session_id": session_id,
        "role": role,
        "text": text,
        "intent": intent,
        "confidence": confidence,
        "action": action,
        "channel": channel,
        "user_hash": user_hash,
    }
    con = _connect()
    con.execute(
        "INSERT INTO events (ts, session_id, role, text, intent, confidence, action, channel, user_hash)"
        " VALUES (:ts, :session_id, :role, :text, :intent, :confidence, :action, :channel, :user_hash)",
        row,
    )
    con.commit()
    con.close()
    with JSONL_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def create_ticket(kind: str, fields: dict, transcript: list, channel: str = "web",
                  reply_to: dict | None = None) -> str:
    """`reply_to` is minimised: how staff can reach the customer back on
    their channel (a hashed id, never the raw one)."""
    prefix = _TICKET_PREFIX.get(kind, "TKT")
    suffix = "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)
    )
    ref = f"{prefix}-{dt.date.today():%Y%m%d}-{suffix}"
    con = _connect()
    con.execute(
        "INSERT INTO tickets (ref, type, created, status, fields, transcript, channel, reply_to)"
        " VALUES (?, ?, ?, 'open', ?, ?, ?, ?)",
        (
            ref,
            kind,
            _now(),
            json.dumps(fields, ensure_ascii=False),
            json.dumps(transcript, ensure_ascii=False),
            channel,
            json.dumps(reply_to, ensure_ascii=False) if reply_to else None,
        ),
    )
    con.commit()
    con.close()
    log_event("-", "system", f"ticket created: {ref}", action=f"ticket:{kind}", channel=channel)
    if config.jira_enabled() and config.jira_configured():
        # P9: a real Jira round trip must not hold up the customer's reply
        # (a 250 ms Jira put /chat p95 at 322 ms). The ticket is already
        # stored above, so the push stays best-effort, as before. Mock mode
        # is a local file write and stays inline.
        threading.Thread(target=_push_to_jira, args=(kind, ref, fields, transcript, channel, reply_to),
                         name=f"jira-push-{ref}", daemon=True).start()
    else:
        _push_to_jira(kind, ref, fields, transcript, channel, reply_to)
    return ref


def _push_to_jira(kind: str, ref: str, fields: dict, transcript: list, channel="web", reply_to=None) -> None:
    """Best-effort: a Jira outage or bad credentials must never block the
    customer-facing ticket flow (§1 rule 1 — no dead ends, extended to us)."""
    try:
        result = jira_export.push_ticket(kind, ref, fields, transcript, channel=channel, reply_to=reply_to)
    except Exception:
        result = None
    if result:
        log_event(
            "-", "system", f"jira issue created: {result['key']} ({result['mode']})",
            action="jira_push",
        )


def purge_expired() -> dict:
    """Retention (§3.3) — periods configurable, to be confirmed by legal.
    Returns how many rows went (counts only, for the housekeeping log)."""
    cutoff = (
        dt.datetime.now(dt.timezone.utc)
        - dt.timedelta(days=config.TRANSCRIPT_RETENTION_DAYS)
    ).isoformat(timespec="seconds")
    con = _connect()
    purged = {"events": con.execute("DELETE FROM events WHERE ts < ?", (cutoff,)).rowcount, "tickets": 0}
    if config.TICKET_RETENTION_DAYS > 0:
        tcut = (
            dt.datetime.now(dt.timezone.utc)
            - dt.timedelta(days=config.TICKET_RETENTION_DAYS)
        ).isoformat(timespec="seconds")
        purged["tickets"] = con.execute("DELETE FROM tickets WHERE created < ?", (tcut,)).rowcount
    con.commit()
    con.close()
    return purged

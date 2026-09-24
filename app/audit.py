"""Structured audit trail (§3.3): SQLite + JSONL, written only AFTER masking.

Also owns tickets (fraud / complaint / callback) with the session transcript
attached, so a human never asks the customer to repeat themselves (§1 rule 7).
"""

import copy
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
        # Date-range reads (admin.report, /admin/analytics) scan by time.
        con.execute("CREATE INDEX IF NOT EXISTS events_ts ON events(ts)")
        con.execute("CREATE INDEX IF NOT EXISTS tickets_created ON tickets(created)")
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
    ("tickets", "jira_key", "TEXT"),  # H2: the agent desk links to it
    # Concern #6: the Jira copy is owed (JIRA_OWED) until a push succeeds;
    # retry_jira() retries it until JIRA_RETRY_HOURS, then gives up
    # (JIRA_ABANDONED). Tickets from before this column are 0: never pushed.
    ("tickets", "jira_pending", "INTEGER NOT NULL DEFAULT 0"),
    ("tickets", "jira_attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("tickets", "jira_next_try", "TEXT"),
]
JIRA_OWED, JIRA_ABANDONED = 1, 2


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
    real_push = config.jira_enabled() and config.jira_configured()
    con = _connect()
    con.execute(
        "INSERT INTO tickets (ref, type, created, status, fields, transcript, channel, reply_to,"
        " jira_pending, jira_next_try) VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)",
        (
            ref,
            kind,
            _now(),
            json.dumps(fields, ensure_ascii=False),
            json.dumps(transcript, ensure_ascii=False),
            channel,
            json.dumps(reply_to, ensure_ascii=False) if reply_to else None,
            # Owed until the push below succeeds. The first retry waits long
            # enough for that push to finish (its timeout is 8 s), so a slow
            # Jira is not sent the same ticket twice.
            JIRA_OWED if real_push else 0,
            _iso_in(config.JIRA_RETRY_FIRST_SECONDS) if real_push else None,
        ),
    )
    con.commit()
    con.close()
    log_event("-", "system", f"ticket created: {ref}", action=f"ticket:{kind}", channel=channel)
    if real_push:
        # P9: a real Jira round trip must not hold up the customer's reply
        # (a 250 ms Jira put /chat p95 at 322 ms). The ticket is already
        # stored above, so the push stays best-effort, as before. Mock mode
        # is a local file write and stays inline. The thread gets its own
        # copies: the caller keeps appending to session.transcript after this
        # returns, and the Jira issue must match the stored ticket exactly.
        snapshot = copy.deepcopy((fields, transcript, reply_to))
        threading.Thread(target=_push_to_jira, args=(kind, ref, snapshot[0], snapshot[1], channel, snapshot[2]),
                         name=f"jira-push-{ref}", daemon=True).start()
    else:
        _push_to_jira(kind, ref, fields, transcript, channel, reply_to)
    return ref


def _push_to_jira(kind: str, ref: str, fields: dict, transcript: list, channel="web", reply_to=None) -> bool:
    """Best-effort: a Jira outage or bad credentials must never block the
    customer-facing ticket flow (§1 rule 1 — no dead ends, extended to us).
    A failed real push leaves the ticket owed, for retry_jira()."""
    try:
        result = jira_export.push_ticket(kind, ref, fields, transcript, channel=channel, reply_to=reply_to)
    except Exception:
        result = None
    try:  # H2: the desk links to the key; never let this block the ticket
        con = _connect()
        if result:
            con.execute("UPDATE tickets SET jira_key = ?, jira_pending = 0 WHERE ref = ?", (result["key"], ref))
        else:
            con.execute("UPDATE tickets SET jira_attempts = jira_attempts + 1 WHERE ref = ? AND jira_pending = ?",
                        (ref, JIRA_OWED))
        con.commit()
        con.close()
    except Exception:
        pass
    if result:
        log_event(
            "-", "system", f"jira issue created: {result['key']} ({result['mode']})",
            action="jira_push",
        )
    return bool(result)


def _iso_in(seconds: float, now: dt.datetime | None = None) -> str:
    moment = (now or dt.datetime.now(dt.timezone.utc)) + dt.timedelta(seconds=seconds)
    return moment.isoformat(timespec="seconds")


def retry_jira(now: dt.datetime | None = None) -> dict:
    """Concern #6: push every ticket whose Jira copy is still owed (the app
    restarted mid-push, or Jira was down). Backs off 5, 10, 20... minutes,
    capped at an hour; after JIRA_RETRY_HOURS it gives up and logs
    `jira_push_abandoned`, and staff copy the ticket from /admin/cases.
    Runs only with real Jira on: nothing is owed in mock mode. A crash just
    after Jira accepted an issue can mean one duplicate issue; that is
    accepted, a missing fraud report is not. Returns counts only."""
    counts = {"pushed": 0, "failed": 0, "abandoned": 0}
    if not (config.jira_enabled() and config.jira_configured()):
        return counts
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = (now - dt.timedelta(hours=config.JIRA_RETRY_HOURS)).isoformat(timespec="seconds")
    con = _connect()
    rows = con.execute(
        "SELECT ref, type, created, fields, transcript, channel, reply_to, jira_attempts FROM tickets"
        " WHERE jira_pending = ? AND jira_key IS NULL AND COALESCE(jira_next_try, '') <= ? ORDER BY created",
        (JIRA_OWED, now.isoformat(timespec="seconds")),
    ).fetchall()
    for ref, kind, created, fields, transcript, channel, reply_to, attempts in rows:
        if created < cutoff:
            con.execute("UPDATE tickets SET jira_pending = ? WHERE ref = ?", (JIRA_ABANDONED, ref))
            con.commit()
            log_event("-", "system", f"jira push abandoned: {ref}", action="jira_push_abandoned", channel=channel)
            counts["abandoned"] += 1
            continue
        wait = min(config.JIRA_RETRY_SECONDS * 2 ** attempts, 3600)
        con.execute("UPDATE tickets SET jira_next_try = ? WHERE ref = ?", (_iso_in(wait, now), ref))
        con.commit()
        pushed = _push_to_jira(kind, ref, json.loads(fields or "{}"), json.loads(transcript or "[]"),
                               channel, json.loads(reply_to) if reply_to else None)
        counts["pushed" if pushed else "failed"] += 1
    con.close()
    return counts


def jira_backlog(now: dt.datetime | None = None) -> dict:
    """For /health: how many tickets still owe their Jira copy, and the age
    of the oldest in minutes. Counts only."""
    now = now or dt.datetime.now(dt.timezone.utc)
    con = _connect()
    count, oldest = con.execute(
        "SELECT COUNT(*), MIN(created) FROM tickets WHERE jira_pending = ? AND jira_key IS NULL", (JIRA_OWED,)
    ).fetchone()
    con.close()
    age = (now - dt.datetime.fromisoformat(oldest)).total_seconds() / 60 if oldest else 0.0
    return {"pending": count, "oldest_pending_minutes": int(age)}


def get_ticket(ref: str) -> dict | None:
    """One ticket's type, channel, fields and Jira key (H2)."""
    con = _connect()
    row = con.execute(
        "SELECT type, channel, fields, jira_key FROM tickets WHERE ref = ?", (ref,)
    ).fetchone()
    con.close()
    if not row:
        return None
    return {"ref": ref, "type": row[0], "channel": row[1],
            "fields": json.loads(row[2]) if row[2] else {}, "jira_key": row[3]}


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

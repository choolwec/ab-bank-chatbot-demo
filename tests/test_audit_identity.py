"""P6: channel column, hashed identities, migration of today's schema."""

import json
import sqlite3

from app import audit, identity, router
from app.session import SessionStore

PRE_P6_SCHEMA = [
    """CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
        session_id TEXT NOT NULL, role TEXT NOT NULL, text TEXT,
        intent TEXT, confidence REAL, action TEXT)""",
    """CREATE TABLE tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT UNIQUE NOT NULL,
        type TEXT NOT NULL, created TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open', fields TEXT, transcript TEXT)""",
]


def test_migration_upgrades_a_pre_p6_database(isolated_data):
    con = sqlite3.connect(audit.DB_FILE)
    for ddl in PRE_P6_SCHEMA:
        con.execute(ddl)
    con.execute("INSERT INTO events (ts, session_id, role, text) VALUES ('t', 's', 'user', 'hi')")
    con.execute("INSERT INTO tickets (ref, type, created) VALUES ('FRD-1', 'fraud', 't')")
    con.commit()
    con.close()

    audit.init_db()  # runs the migration
    audit.log_event("s2", "user", "hello", channel="whatsapp", user_hash="abc")

    con = sqlite3.connect(audit.DB_FILE)
    rows = con.execute("SELECT session_id, channel, user_hash FROM events ORDER BY id").fetchall()
    ticket = con.execute("SELECT channel, reply_to FROM tickets WHERE ref = 'FRD-1'").fetchone()
    con.close()
    assert rows == [("s", "web", None), ("s2", "whatsapp", "abc")]
    assert ticket == ("web", None)


def test_migration_is_idempotent(isolated_data):
    audit.init_db()
    con = sqlite3.connect(audit.DB_FILE)
    audit._migrate(con)
    audit._migrate(con)
    cols = [r[1] for r in con.execute("PRAGMA table_info(events)")]
    con.close()
    assert cols.count("channel") == 1


def test_hmac_is_stable_and_keyed(monkeypatch):
    monkeypatch.setenv("USER_KEY_SECRET", "secret-one")
    a = identity.user_hash("whatsapp:260977123456")
    assert a == identity.user_hash("whatsapp:260977123456")
    assert len(a) == 32 and "260977123456" not in a
    assert a != identity.user_hash("whatsapp:260977123457")
    monkeypatch.setenv("USER_KEY_SECRET", "secret-two")
    assert identity.user_hash("whatsapp:260977123456") != a


def test_no_raw_platform_id_anywhere_in_the_audit_log(isolated_data):
    raw = "260977123456"
    store = SessionStore()
    with store.session(f"whatsapp:{raw}", "whatsapp") as (session, _):
        router.welcome(session)
        router.handle(session, text="i think i was scammed")
        router.handle(session, text="they called pretending to be the bank")
        router.handle(session, text="yesterday")
        router.handle(session, text="eTumba")
        router.handle(session, text="skip")
        assert raw not in session.id
    con = sqlite3.connect(audit.DB_FILE)
    events = con.execute("SELECT session_id, user_hash, channel, text FROM events").fetchall()
    tickets = con.execute("SELECT channel, reply_to, fields FROM tickets").fetchall()
    con.close()
    assert events and all(raw not in (sid or "") and raw not in (h or "") for sid, h, _, _ in events)
    assert {ch for _, _, ch, _ in events if ch} >= {"whatsapp"}
    assert raw not in audit.JSONL_FILE.read_text(encoding="utf-8")
    (channel, reply_to, _fields), = tickets
    assert channel == "whatsapp"
    reply = json.loads(reply_to)
    assert reply["channel"] == "whatsapp" and len(reply["user_hash"]) == 32
    assert raw not in reply_to


def test_web_events_carry_the_session_hash(bot):
    b = bot()
    b.say("what is etumba")
    rows = [json.loads(l) for l in audit.JSONL_FILE.read_text(encoding="utf-8").splitlines()]
    mine = [r for r in rows if r["session_id"] == b.session.id]
    assert mine and all(r["channel"] == "web" and r["user_hash"] == b.session.user_hash for r in mine)

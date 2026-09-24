"""P1: the persistent session store."""

import threading
import time

import pytest

from app import config
from app.session import SessionStore, SqliteSessionStore


@pytest.fixture
def db(tmp_path):
    return tmp_path / "sessions.db"


def _age(store, key, seconds):
    """Pretend the session was last active `seconds` ago."""
    s = store._load(key)
    s.last_active -= seconds
    s.flow_touched = (s.flow_touched or s.last_active) - seconds
    store._save(key, s)


def test_survives_a_restart(db):
    store = SqliteSessionStore(db)
    with store.session("whatsapp:u1", "whatsapp") as (s, created):
        assert created
        s.active_flow = "fraud"
        s.flow_state = {"step": 2, "data": {"what_happened": "they took K500"}}
        s.add("user", "they took K500")
        sid = s.id
    reopened = SqliteSessionStore(db)  # a new process
    with reopened.session("whatsapp:u1", "whatsapp") as (s, created):
        assert not created
        assert s.id == sid
        assert s.flow_state["data"]["what_happened"] == "they took K500"
        assert s.transcript[-1]["text"] == "they took K500"


def test_web_session_ids_resume_and_unknown_ids_start_fresh(db):
    store = SqliteSessionStore(db)
    with store.web_session(None) as (s, created):
        sid = s.id
    with store.web_session(sid) as (s, created):
        assert not created and s.id == sid
    with store.web_session("not-a-real-id") as (s, created):
        assert created and s.id != sid


def test_idle_regreet_keeps_the_flow(db):
    store = SqliteSessionStore(db)
    with store.session("web:x") as (s, _):
        s.active_flow = "lead"
        s.flow_state = {"step": 1, "data": {"name": "Mary"}}
    _age(store, "web:x", (config.IDLE_REGREET_MINUTES + 5) * 60)
    with store.session("web:x") as (s, _):
        assert s.returning
        assert s.active_flow == "lead" and s.flow_state["data"] == {"name": "Mary"}


@pytest.mark.parametrize(
    "flow,hours,kept",
    [
        ("lead", config.FLOW_EXPIRY_HOURS - 1, True),
        ("lead", config.FLOW_EXPIRY_HOURS + 1, False),
        ("fraud", config.FLOW_EXPIRY_HOURS + 1, True),   # fraud reports last longer
        ("complaint", config.FLOW_EXPIRY_HOURS_URGENT - 1, True),
        ("fraud", config.FLOW_EXPIRY_HOURS_URGENT + 1, False),
    ],
)
def test_flow_expiry(db, flow, hours, kept):
    store = SqliteSessionStore(db)
    with store.session("web:y") as (s, _):
        s.active_flow = flow
        s.flow_state = {"step": 1, "data": {"x": "y"}}
    _age(store, "web:y", hours * 3600)
    with store.session("web:y") as (s, _):
        assert (s.active_flow == flow) is kept


def test_concurrent_writes_to_one_session_never_lose_a_turn(db):
    store = SqliteSessionStore(db)
    with store.session("web:z"):
        pass

    def worker(n):
        for i in range(10):
            with store.session("web:z") as (s, _):
                count = s.slots.get("count", 0)
                time.sleep(0.001)  # widen the race window
                s.slots["count"] = count + 1
                s.add("user", f"{n}-{i}")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with store.session("web:z") as (s, _):
        assert s.slots["count"] == 50
        assert len(s.transcript) == 50


def test_purge_follows_transcript_retention(db, monkeypatch):
    store = SqliteSessionStore(db)
    with store.session("web:old"):
        pass
    with store.session("web:new"):
        pass
    _age(store, "web:old", (config.TRANSCRIPT_RETENTION_DAYS + 1) * 86400)
    assert store.purge_expired() == 1
    assert store.count() == 1
    assert store._load("web:old") is None


def test_in_memory_store_has_the_same_rules():
    store = SessionStore()
    with store.session("web:m") as (s, created):
        assert created
        s.active_flow = "lead"
        s.flow_state = {"step": 0, "data": {}}
    _age(store, "web:m", (config.FLOW_EXPIRY_HOURS + 1) * 3600)
    with store.session("web:m") as (s, created):
        assert not created and s.active_flow is None


def test_widget_reopened_after_idle_welcomes_but_keeps_a_flow(client, monkeypatch):
    from conftest import chat

    from app.session import store

    sid = chat(client)["session_id"]
    chat(client, sid, payload="human_handoff")
    chat(client, sid, message="Mary")
    _age(store, f"web:{sid}", (config.IDLE_REGREET_MINUTES + 5) * 60)
    data = chat(client, sid)  # widget reopened
    assert data["meta"]["action"] == "resume_flow"
    assert "phone number" in " ".join(r["text"] for r in data["replies"]).lower()

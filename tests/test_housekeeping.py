"""R1: the retention purges run at start-up and every night, and include the
webhook inbox (which nothing purged before)."""

import asyncio
import datetime as dt
import sqlite3
import time

import pytest

from app import audit, config, hours, housekeeping, inbox as inbox_mod, main
from app import session as session_mod
from app.channels.base import InboundMessage


@pytest.fixture
def stores(tmp_path, monkeypatch, isolated_data):
    box = inbox_mod.Inbox(tmp_path / "inbox.db")
    store = session_mod.SqliteSessionStore(tmp_path / "sessions.db")
    monkeypatch.setattr(inbox_mod, "inbox", box)
    monkeypatch.setattr(session_mod, "store", store)
    return box, store


def _row(box, msg_id, status, days_old):
    box.store(InboundMessage(channel="whatsapp", user_key="260977000111", text="hi", msg_id=msg_id))
    with sqlite3.connect(box.path) as con:
        con.execute("UPDATE inbound SET status = ?, received = ? WHERE id = ?",
                    (status, time.time() - days_old * 86400, f"whatsapp:{msg_id}"))


def test_purge_all_covers_audit_sessions_and_inbox(stores, monkeypatch):
    box, store = stores
    monkeypatch.setattr(config, "TRANSCRIPT_RETENTION_DAYS", 30)
    _row(box, "old-done", "done", 31)
    _row(box, "old-failed", "failed", 31)
    _row(box, "old-new", "new", 31)  # never answered: never purged
    _row(box, "recent-done", "done", 1)
    with store.session("whatsapp:abc", "whatsapp") as (session, _):
        pass
    with sqlite3.connect(store.path) as con:
        con.execute("UPDATE sessions SET last_active = ?", (time.time() - 31 * 86400,))
    audit.log_event("s1", "user", "hello")
    con = sqlite3.connect(audit.DB_FILE)
    con.execute("UPDATE events SET ts = ?", ((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=31)).isoformat(),))
    con.commit()
    con.close()

    purged = housekeeping.purge_all()

    assert purged == {"events": 1, "tickets": 0, "sessions": 1, "inbox": 2, "desk_links": 0}
    with sqlite3.connect(box.path) as con:
        left = {row[0] for row in con.execute("SELECT id FROM inbound")}
    assert left == {"whatsapp:old-new", "whatsapp:recent-done"}
    assert store.count() == 0


def test_lifespan_runs_the_purge_and_starts_the_nightly_job(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "purge_all", lambda: calls.append("purge") or {})
    monkeypatch.setattr(main.worker, "start", lambda: calls.append("worker"))
    monkeypatch.setattr(main.housekeeper, "start", lambda: calls.append("housekeeper"))

    async def stopped():
        calls.append("stopped")

    monkeypatch.setattr(main.worker, "stop", stopped)
    monkeypatch.setattr(main.housekeeper, "stop", stopped)

    async def go():
        async with main.lifespan(main.app):
            calls.append("serving")

    asyncio.run(go())
    assert calls == ["purge", "worker", "housekeeper", "serving", "stopped", "stopped"]


@pytest.mark.parametrize("now, expected_hours", [
    (dt.datetime(2026, 9, 23, 10, 0, tzinfo=hours.LUSAKA), 16),
    (dt.datetime(2026, 9, 23, 1, 0, tzinfo=hours.LUSAKA), 1),
    (dt.datetime(2026, 9, 23, 2, 0, tzinfo=hours.LUSAKA), 24),
    (dt.datetime(2026, 9, 23, 0, 0, tzinfo=dt.timezone.utc), 24),  # 02:00 Lusaka exactly
])
def test_next_run_is_the_next_purge_hour_in_lusaka(now, expected_hours):
    assert housekeeping.seconds_until_next_run(now) == expected_hours * 3600


def test_the_nightly_loop_purges_and_survives_a_failure(monkeypatch):
    runs = []

    def purge():
        runs.append(1)
        if len(runs) == 1:
            raise sqlite3.OperationalError("locked")  # the loop must carry on
        return {}

    monkeypatch.setattr(housekeeping, "purge_all", purge)
    monkeypatch.setattr(housekeeping, "seconds_until_next_run", lambda now=None: 0)

    async def go():
        keeper = housekeeping.Housekeeper()
        keeper.start()
        for _ in range(200):
            if len(runs) >= 3:
                break
            await asyncio.sleep(0.01)
        await keeper.stop()

    asyncio.run(go())
    assert len(runs) >= 3


def test_the_nightly_loop_waits_for_the_purge_hour(monkeypatch):
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(housekeeping.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(housekeeping, "purge_all", lambda: pytest.fail("purged before the purge hour"))

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(housekeeping.Housekeeper()._run())
    assert waits == [16 * 3600]  # the suite runs at 10:00 Lusaka (conftest)

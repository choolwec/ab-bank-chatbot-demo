"""P7: REPLY_KEY holds several keys (MultiFernet) and can be rotated."""

import json
import sqlite3

import pytest
from cryptography.fernet import Fernet, InvalidToken

from admin import rotate_reply_key
from app import audit, identity
from app.channels.base import InboundMessage
from app.inbox import Inbox
from app.session import SqliteSessionStore

OLD, NEW, GONE = (Fernet.generate_key().decode() for _ in range(3))
WA_ID = "260977000001"


def test_first_key_seals_and_every_key_unseals(monkeypatch):
    monkeypatch.setenv("REPLY_KEY", OLD)
    old_token = identity.seal(WA_ID)
    monkeypatch.setenv("REPLY_KEY", f"{NEW},{OLD}")
    assert identity.unseal(old_token) == WA_ID
    assert not identity.sealed_with_primary(old_token)
    new_token = identity.seal(WA_ID)
    assert identity.sealed_with_primary(new_token)
    assert Fernet(NEW.encode()).decrypt(new_token.encode()).decode() == WA_ID
    monkeypatch.setenv("REPLY_KEY", NEW)
    with pytest.raises(InvalidToken):
        identity.unseal(old_token)  # retire a key only after rotating


def test_keys_may_be_separated_by_commas_or_newlines(monkeypatch):
    assert identity.reply_keys(f" {NEW} ,\n{OLD}\n") == [NEW.encode(), OLD.encode()]
    monkeypatch.setenv("REPLY_KEY", " , ")
    with pytest.raises(ValueError):
        identity.seal(WA_ID)


def test_reseal_moves_a_value_to_the_primary_key(monkeypatch):
    monkeypatch.setenv("REPLY_KEY", OLD)
    token = identity.seal(WA_ID)
    monkeypatch.setenv("REPLY_KEY", f"{NEW},{OLD}")
    fresh = identity.reseal(token)
    assert identity.sealed_with_primary(fresh)
    monkeypatch.setenv("REPLY_KEY", NEW)
    assert identity.unseal(fresh) == WA_ID


def _seed(tmp_path):
    """One of each stored sealed value, all sealed with whatever key is set."""
    box = Inbox(tmp_path / "inbox.db")
    box.store(InboundMessage(channel="whatsapp", user_key=WA_ID, text="hi", msg_id="wamid.R1",
                             phone_hint=WA_ID))
    store = SqliteSessionStore(tmp_path / "sessions.db")
    with store.session(f"whatsapp:{WA_ID}", "whatsapp") as (session, _):
        session.slots["reply_ref"] = identity.seal(WA_ID)
        session.slots["phone_hint_ref"] = identity.seal(WA_ID)
    ref = audit.create_ticket("callback", {"name": "Test"}, [], channel="whatsapp",
                              reply_to={"channel": "whatsapp", "sealed": identity.seal(WA_ID)})
    return box, store, ref


def _all_sealed(tmp_path, ref):
    con = sqlite3.connect(tmp_path / "inbox.db")
    user_ref, message = con.execute("SELECT user_ref, message FROM inbound").fetchone()
    con.close()
    con = sqlite3.connect(tmp_path / "sessions.db")
    state = json.loads(con.execute("SELECT state FROM sessions").fetchone()[0])
    con.close()
    con = sqlite3.connect(audit.DB_FILE)
    reply_to = json.loads(con.execute("SELECT reply_to FROM tickets WHERE ref = ?", (ref,)).fetchone()[0])
    con.close()
    return [user_ref, json.loads(message)["phone_hint"], state["slots"]["reply_ref"],
            state["slots"]["phone_hint_ref"], reply_to["sealed"]]


def test_rotation_reseals_every_stored_value(isolated_data, monkeypatch):
    monkeypatch.setenv("REPLY_KEY", OLD)
    box, store, ref = _seed(isolated_data)
    monkeypatch.setenv("REPLY_KEY", f"{NEW},{OLD}")

    check = rotate_reply_key.rotate(check=True)
    assert sum(t.old for t in check.values()) == 5
    dry = rotate_reply_key.rotate(dry_run=True)
    assert sum(t.resealed for t in dry.values()) == 5
    assert not any(identity.sealed_with_primary(t) for t in _all_sealed(isolated_data, ref))

    results = rotate_reply_key.rotate()
    assert {name: t.resealed for name, t in results.items()} == {"inbox.db": 2, "sessions.db": 2, "audit.db": 1}
    assert sum(t.old for t in rotate_reply_key.rotate(check=True).values()) == 0
    assert sum(t.resealed for t in rotate_reply_key.rotate().values()) == 0  # idempotent

    monkeypatch.setenv("REPLY_KEY", NEW)  # the old key is retired
    assert [identity.unseal(t) for t in _all_sealed(isolated_data, ref)] == [WA_ID] * 5
    seen = []
    box.process_pending(lambda msg, findings: seen.append((msg.user_key, msg.phone_hint)))
    assert seen == [(WA_ID, WA_ID)]


def test_a_value_no_key_opens_is_left_alone_and_reported(isolated_data, monkeypatch):
    monkeypatch.setenv("REPLY_KEY", GONE)
    _, _, ref = _seed(isolated_data)
    before = _all_sealed(isolated_data, ref)
    monkeypatch.setenv("REPLY_KEY", f"{NEW},{OLD}")
    results = rotate_reply_key.rotate()
    assert sum(t.unreadable for t in results.values()) == 5
    assert sum(t.resealed for t in results.values()) == 0
    assert _all_sealed(isolated_data, ref) == before


def test_a_row_changed_meanwhile_is_never_overwritten(isolated_data, monkeypatch):
    monkeypatch.setenv("REPLY_KEY", OLD)
    _seed(isolated_data)
    path = isolated_data / "sessions.db"
    con = sqlite3.connect(path)
    key, state = con.execute("SELECT key, state FROM sessions").fetchone()
    con.execute("UPDATE sessions SET state = ? WHERE key = ?", (state.replace('"strikes": 0', '"strikes": 1'), key))
    con.commit()
    tally = rotate_reply_key.Tally()
    rotate_reply_key._apply(con, [("UPDATE sessions SET state = ? WHERE key = ? AND state = ?",
                                   ("{}", key, state), 2)], tally, dry_run=False)
    assert (tally.changed, tally.resealed) == (1, 0)
    assert '"strikes": 1' in con.execute("SELECT state FROM sessions").fetchone()[0]
    con.close()


def test_the_command_prints_counts_never_values(isolated_data, monkeypatch, capsys):
    monkeypatch.setenv("REPLY_KEY", OLD)
    _, _, ref = _seed(isolated_data)
    tokens = _all_sealed(isolated_data, ref)
    monkeypatch.setenv("REPLY_KEY", f"{NEW},{OLD}")
    monkeypatch.setattr("sys.argv", ["rotate_reply_key"])
    with pytest.raises(SystemExit) as done:
        rotate_reply_key.main()
    assert done.value.code == 0
    out = capsys.readouterr().out
    assert "2 key(s) configured" in out and "sessions.db: 2 re-sealed" in out
    for secret in [WA_ID, OLD, NEW, *tokens]:
        assert secret not in out

    monkeypatch.setattr("sys.argv", ["rotate_reply_key", "--check"])
    with pytest.raises(SystemExit) as done:
        rotate_reply_key.main()
    assert done.value.code == 0


def test_check_fails_while_values_remain_on_an_old_key(isolated_data, monkeypatch):
    monkeypatch.setenv("REPLY_KEY", OLD)
    _seed(isolated_data)
    monkeypatch.setenv("REPLY_KEY", f"{NEW},{OLD}")
    monkeypatch.setattr("sys.argv", ["rotate_reply_key", "--check"])
    with pytest.raises(SystemExit) as done:
        rotate_reply_key.main()
    assert done.value.code == 1


def test_generate_prints_a_usable_key(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["rotate_reply_key", "--generate"])
    rotate_reply_key.main()
    key = capsys.readouterr().out.strip()
    assert Fernet(key.encode())


def test_refuses_to_run_without_a_key(isolated_data, monkeypatch):
    """No REPLY_KEY and no key file means the wrong environment: never
    generate a fresh key, which would orphan every stored value."""
    monkeypatch.delenv("REPLY_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["rotate_reply_key"])
    with pytest.raises(SystemExit) as done:
        rotate_reply_key.main()
    assert done.value.code == 2
    assert not (isolated_data / "reply_key").exists()

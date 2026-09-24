"""WhatsApp coexistence pause (W11): staff replying from the WhatsApp Business
app pause the bot for that customer. Driven through the signed webhook, the
durable inbox and the worker, with recorded payloads (tests/data/wa/)."""

import json
import sqlite3
import time
from pathlib import Path

import pytest

from app import audit, config, guards
from app.channels import coexistence, messaging, whatsapp
from app.channels.base import InboundMessage

WA = Path(__file__).parent / "data" / "wa"
RAW_NUMBER = "260977123456"
KEY = messaging.session_key(InboundMessage("whatsapp", RAW_NUMBER))
STAFF_TEXT = "this is Mary at AB Bank"
STAFF_NUMBER = "0977 555 010"
HOURS = config.COEXISTENCE_PAUSE_HOURS_DEFAULT


@pytest.fixture
def coexist(meta_env, monkeypatch):
    monkeypatch.setenv("COEXISTENCE_ENABLED", "true")
    monkeypatch.delenv("COEXISTENCE_PAUSE_HOURS", raising=False)
    return meta_env


def _body(name, ts=None):
    raw = (WA / f"{name}.json").read_text(encoding="utf-8").replace("TS", str(int(ts or time.time())))
    return json.loads(raw)


def echo(env, ts=None, msg_id=None):
    """A person replied to the customer from the Business app."""
    body = _body("echo", ts)
    body["entry"][0]["changes"][0]["value"]["message_echoes"][0]["id"] = msg_id or f"wamid.E{time.time_ns()}"
    assert env.post("whatsapp", body).status_code == 200
    env.process()


def say(env, text=None, button=None):
    """One message from the customer."""
    body = _body("button_reply" if button else "text")
    m = body["entry"][0]["changes"][0]["value"]["messages"][0]
    m["id"] = f"wamid.{time.time_ns()}"
    if button:
        m["interactive"]["button_reply"]["id"] = button
    else:
        m["text"] = {"body": text}
    assert env.post("whatsapp", body).status_code == 200
    env.process()


def state(env):
    with env.store.session(KEY, "whatsapp") as (session, created):
        assert not created
        return session


def events(action=None):
    if not audit.JSONL_FILE.exists():
        return []
    rows = [json.loads(line) for line in audit.JSONL_FILE.read_text(encoding="utf-8").splitlines()]
    return [r for r in rows if action is None or r["action"] == action]


def tickets():
    return sqlite3.connect(audit.DB_FILE).execute("SELECT ref, type, fields FROM tickets").fetchall()


def sent(env):
    return len(env.sent_texts("whatsapp"))


# --- parsing ---------------------------------------------------------------------------


def test_an_echo_parses_to_the_customer_and_keeps_no_text():
    now = time.time()
    (m,), statuses = whatsapp.parse(_body("echo", now))
    assert statuses == []
    assert m.kind == "echo" and m.user_key == RAW_NUMBER and m.msg_id == "echo:wamid.ECHO1"
    assert m.text is None and m.payload is None and m.phone_hint is None
    assert abs(m.ts - now) < 2


def test_an_echo_uses_the_bsuid_like_the_customers_own_messages():
    body = _body("echo")
    value = body["entry"][0]["changes"][0]["value"]
    value["contacts"] = [{"wa_id": RAW_NUMBER, "user_id": "ZM.BSUID.abc123"}]
    (m,), _ = whatsapp.parse(body)
    assert m.user_key == "ZM.BSUID.abc123"
    value.pop("contacts")
    value["message_echoes"][0]["to_user_id"] = "ZM.BSUID.xyz"
    (m,), _ = whatsapp.parse(body)
    assert m.user_key == "ZM.BSUID.xyz"


# --- pausing -----------------------------------------------------------------------------


def test_an_echo_pauses_the_bot(coexist):
    say(coexist, "hi")
    before = sent(coexist)
    window = state(coexist).last_inbound_at
    echo(coexist)
    session = state(coexist)
    assert session.bot_paused_until == pytest.approx(time.time() + HOURS * 3600, abs=30)
    assert coexistence.PAUSED_SLOT in session.slots
    assert session.last_inbound_at == window  # a staff reply does not open the 24-h window
    assert sent(coexist) == before  # nothing sent for the echo itself
    (event,) = events("human_reply_echo")
    assert event["user_hash"] == session.user_hash
    assert STAFF_TEXT not in json.dumps(event) and RAW_NUMBER not in json.dumps(event)


def test_an_echo_for_a_new_customer_pauses_before_they_write(coexist):
    echo(coexist)  # staff started the chat from the app
    say(coexist, "what is etumba")
    assert sent(coexist) == 0


def test_the_pause_length_is_configurable(coexist, monkeypatch):
    monkeypatch.setenv("COEXISTENCE_PAUSE_HOURS", "2")
    echo(coexist)
    assert state(coexist).bot_paused_until == pytest.approx(time.time() + 2 * 3600, abs=30)


def test_messages_while_paused_get_no_reply_and_are_logged_masked(coexist):
    say(coexist, "hi")
    echo(coexist)
    before = sent(coexist)
    say(coexist, "what is etumba")
    say(coexist, "my card number is 4111 1111 1111 1111 can you check it")
    assert sent(coexist) == before
    assert len(events("paused")) == 2
    user_turns = [e["text"] for e in events() if e["role"] == "user"]
    assert "what is etumba" in user_turns
    log = audit.JSONL_FILE.read_text(encoding="utf-8")
    assert "4111" not in log and "1111 1111" not in log
    assert user_turns[-1] == "my card number is [CARD REDACTED] can you check it"


def test_a_new_echo_extends_the_pause(coexist):
    echo(coexist, ts=time.time() - 6 * 3600)
    first = state(coexist).bot_paused_until
    assert first == pytest.approx(time.time() + (HOURS - 6) * 3600, abs=30)
    echo(coexist)
    second = state(coexist).bot_paused_until
    assert second == pytest.approx(time.time() + HOURS * 3600, abs=30)
    assert len(events("human_reply_echo")) == 2


def test_a_late_redelivered_echo_does_not_pause(coexist):
    echo(coexist, ts=time.time() - (HOURS + 1) * 3600)
    say(coexist, "what is etumba")
    assert any("mobile wallet" in t for t in coexist.sent_texts("whatsapp"))
    assert events("human_reply_echo_stale")


def test_a_duplicate_echo_is_processed_once(coexist):
    echo(coexist, msg_id="wamid.SAME")
    echo(coexist, msg_id="wamid.SAME")
    assert len(events("human_reply_echo")) == 1


def test_an_echo_never_shortens_a_longer_pause(coexist):
    say(coexist, "hi")
    with coexist.store.session(KEY, "whatsapp") as (session, _):
        session.bot_paused_until = time.time() + 48 * 3600  # e.g. an agent-desk pause
    echo(coexist)
    assert state(coexist).bot_paused_until > time.time() + 47 * 3600


# --- resuming ----------------------------------------------------------------------------


def test_the_bot_resumes_after_the_timeout(coexist):
    say(coexist, "hi")
    echo(coexist)
    with coexist.store.session(KEY, "whatsapp") as (session, _):
        session.bot_paused_until = time.time() - 1  # COEXISTENCE_PAUSE_HOURS with no new echo
    say(coexist, "what is etumba")
    assert "mobile wallet" in coexist.sent_texts("whatsapp")[-1]
    session = state(coexist)
    assert coexistence.PAUSED_SLOT not in session.slots and session.bot_paused_until == 0
    (event,) = events("coexistence_resumed")
    assert "timeout" in event["text"]


@pytest.mark.parametrize("how", ["typed", "tapped"])
def test_the_bot_resumes_on_menu(coexist, how):
    say(coexist, "hi")
    echo(coexist)
    before = sent(coexist)
    if how == "typed":
        say(coexist, "Menu")
    else:
        say(coexist, button="menu")
    assert sent(coexist) == before + 1  # the menu, straight away
    session = state(coexist)
    assert session.bot_paused_until == 0 and coexistence.PAUSED_SLOT not in session.slots
    assert events("coexistence_resumed")
    say(coexist, "what is etumba")
    assert "mobile wallet" in coexist.sent_texts("whatsapp")[-1]


def test_menu_inside_a_sentence_does_not_resume(coexist):
    echo(coexist)
    say(coexist, "can you send me the menu of your loan products")
    assert sent(coexist) == 0 and not events("coexistence_resumed")


# --- urgent messages while paused ---------------------------------------------------------


def test_an_urgent_message_while_paused_still_creates_a_fraud_ticket(coexist):
    say(coexist, "hi")
    echo(coexist)
    before = sent(coexist)
    assert guards.urgent_scan("someone stole my card").is_hard
    say(coexist, "someone stole my card")
    ((ref, kind, fields),) = tickets()
    fields = json.loads(fields)
    assert kind == "fraud" and fields["what_happened"] == "someone stole my card"
    assert fields["reported_while"] == coexistence.REPORTED_WHILE
    jira = [json.loads(line) for line in (coexist.tmp / "jira_mock.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(ref in issue["summary"] for issue in jira)
    # one short safety reply with the reference and the emergency route
    texts = coexist.sent_texts("whatsapp")
    assert len(texts) == before + 1 and ref in texts[-1]
    assert "block" in texts[-1]
    assert events("coexistence_urgent") and events("paused")
    session = state(coexist)
    assert session.bot_paused_until > time.time()  # still paused: staff keep the conversation
    assert session.active_flow is None


def test_further_urgent_messages_in_the_same_pause_do_not_repeat(coexist):
    echo(coexist)
    say(coexist, "someone stole my card")
    count = sent(coexist)
    say(coexist, "I have been scammed please block my card")
    assert len(tickets()) == 1 and sent(coexist) == count
    assert events("coexistence_urgent_repeat")


def test_a_soft_signal_while_paused_is_only_logged(coexist):
    text = "how do i protect myself from scams"
    signal = guards.urgent_scan(text)
    assert signal is None or not signal.is_hard
    echo(coexist)
    say(coexist, text)
    assert tickets() == [] and sent(coexist) == 0


def test_an_unfinished_fraud_report_is_ticketed_when_staff_take_over(coexist):
    say(coexist, "someone stole my card")
    say(coexist, "it was taken from my bag at the market")
    assert state(coexist).active_flow == "fraud"
    echo(coexist)
    ((ref, kind, fields),) = tickets()
    fields = json.loads(fields)
    assert kind == "fraud" and fields["unfinished"] == "yes"
    assert "market" in fields["what_happened"]
    assert state(coexist).active_flow is None
    assert events("coexistence_unfinished_ticket")


# --- the flag -------------------------------------------------------------------------------


def test_with_the_flag_off_echoes_are_ignored_and_logged(meta_env, monkeypatch):
    monkeypatch.delenv("COEXISTENCE_ENABLED", raising=False)
    assert config.coexistence_enabled() is False  # the default, and flags.json
    say(meta_env, "hi")
    echo(meta_env)
    session = state(meta_env)
    assert session.bot_paused_until == 0 and coexistence.PAUSED_SLOT not in session.slots
    assert events("human_reply_echo_ignored") and not events("human_reply_echo")
    say(meta_env, "what is etumba")
    assert "mobile wallet" in meta_env.sent_texts("whatsapp")[-1]
    say(meta_env, "someone stole my card")
    assert state(meta_env).active_flow == "fraud"  # the normal flow, as today


def test_turning_the_flag_off_lifts_a_running_pause(coexist, monkeypatch):
    say(coexist, "hi")
    echo(coexist)
    monkeypatch.setenv("COEXISTENCE_ENABLED", "false")
    say(coexist, "what is etumba")
    assert "mobile wallet" in coexist.sent_texts("whatsapp")[-1]
    assert "switched off" in events("coexistence_resumed")[0]["text"]


# --- security and privacy ----------------------------------------------------------------------


def test_a_bad_signature_on_an_echo_is_rejected(coexist):
    body = _body("echo")
    assert coexist.post("whatsapp", body, signature="sha256=deadbeef").status_code == 401
    assert coexist.post("whatsapp", body, signature="").status_code == 401
    assert coexist.inbox.counts() == {}
    coexist.process()
    assert not events("human_reply_echo")
    with coexist.store.session(KEY, "whatsapp") as (session, created):
        assert created and session.bot_paused_until == 0


def test_no_raw_number_wa_id_or_staff_text_is_stored(coexist):
    say(coexist, "hi")
    echo(coexist)
    say(coexist, "what is etumba")
    say(coexist, "someone stole my card")
    echo(coexist)
    say(coexist, "menu")
    for path in (audit.JSONL_FILE, audit.DB_FILE, coexist.tmp / "sessions.db", coexist.tmp / "inbox.db",
                 coexist.tmp / "jira_mock.jsonl"):
        data = path.read_bytes()
        assert RAW_NUMBER.encode() not in data, path
        assert STAFF_TEXT.encode() not in data and STAFF_NUMBER.encode() not in data, path
    for (text,) in sqlite3.connect(audit.DB_FILE).execute("SELECT text FROM events"):
        assert RAW_NUMBER not in (text or "")

"""H5: sampled one-tap CSAT after a resolved conversation.

The suite runs with CSAT_SAMPLE_RATE=0 (conftest); these tests turn it on.
"""

import hashlib
import json
import sqlite3

import pytest

from app import audit, config, render
from app.router import CSAT_DOWN, CSAT_UP, MENU_BUTTONS, csat_sampled

# Bucket 0 is inside any sample above 0; 0xffffffff % 10000 = 7295 is outside 20%.
SAMPLED = "0" * 32
NOT_SAMPLED = "f" * 32

CALLBACK = [("tap", "human_handoff"), ("say", "Mary Banda"), ("say", "0977123456"),
            ("say", "a loan"), ("tap", "time:Morning"), ("tap", "confirm_yes")]
COMPLAINT = [("say", "I want to complain"), ("say", "Service at a branch"),
             ("say", "I waited two hours and nobody helped me"), ("say", "skip"),
             ("tap", "confirm_yes")]
FRAUD = [("say", "someone stole money from my etumba"), ("say", "yes"),
         ("say", "yesterday"), ("say", "0977123456")]


@pytest.fixture
def rate(monkeypatch):
    def set_rate(value):
        monkeypatch.setenv("CSAT_SAMPLE_RATE", str(value))
    set_rate(0.2)
    return set_rate


def _run(b, steps):
    for kind, value in steps:
        b.say(value) if kind == "say" else b.tap(value)
    return b


def _customer(bot, user_hash=SAMPLED, channel="web"):
    b = bot(channel=channel)
    b.session.user_hash = user_hash
    return b


def _asked(b):
    return b.last[1].get("csat") == "asked"


def _events(action):
    con = sqlite3.connect(audit.DB_FILE)
    rows = con.execute(
        "SELECT role, channel, user_hash, text FROM events WHERE action = ?", (action,)
    ).fetchall()
    con.close()
    return rows


# --- sampling ---------------------------------------------------------------


class _S:
    def __init__(self, user_hash):
        self.user_hash = user_hash


def test_sample_is_deterministic_per_customer(rate):
    assert csat_sampled(_S(SAMPLED)) and csat_sampled(_S(SAMPLED))
    assert not csat_sampled(_S(NOT_SAMPLED))
    rate(0)
    assert not csat_sampled(_S(SAMPLED))
    rate(1)
    assert csat_sampled(_S(NOT_SAMPLED))
    assert not csat_sampled(_S("")), "no identity: never asked"


def test_sample_is_about_one_in_five(rate):
    hashes = [hashlib.sha256(str(i).encode()).hexdigest()[:32] for i in range(10_000)]
    share = sum(csat_sampled(_S(h)) for h in hashes) / len(hashes)
    assert 0.18 < share < 0.22, share


def test_rate_comes_from_env_then_flags_file_then_default(monkeypatch, tmp_path):
    flags = tmp_path / "flags.json"
    monkeypatch.setattr(config, "FLAGS_FILE", flags)
    monkeypatch.delenv("CSAT_SAMPLE_RATE", raising=False)
    assert config.csat_sample_rate() == config.CSAT_SAMPLE_RATE_DEFAULT == 0.2
    flags.write_text(json.dumps({"CSAT_SAMPLE_RATE": 0.05}), encoding="utf-8")
    assert config.csat_sample_rate() == 0.05
    monkeypatch.setenv("CSAT_SAMPLE_RATE", "0.5")
    assert config.csat_sample_rate() == 0.5  # env wins
    monkeypatch.setenv("CSAT_SAMPLE_RATE", "lots")
    assert config.csat_sample_rate() == 0.2  # unreadable: the default
    monkeypatch.setenv("CSAT_SAMPLE_RATE", "7")
    assert config.csat_sample_rate() == 1.0  # clamped


# --- when it is asked -----------------------------------------------------------


def test_sampled_customer_is_asked_once_after_goodbye(bot, rate):
    b = _customer(bot)
    b.say("what is etumba")
    b.say("thanks")
    assert _asked(b)
    ask = b.last[0][-1]
    assert b.buttons == [CSAT_UP, CSAT_DOWN, "menu"]
    assert "tell us how I did" in ask["text"]
    assert b.session.slots["csat_asked"] == "thanks_goodbye"
    (event,) = _events("csat_asked")
    assert event[1] == "web" and event[2] == SAMPLED

    b.say("what are your opening hours")
    b.say("thank you")
    assert b.last[1].get("intent") == "thanks_goodbye"
    assert not _asked(b) and CSAT_UP not in b.buttons
    assert len(_events("csat_asked")) == 1


def test_non_sampled_customer_is_never_asked(bot, rate):
    b = _customer(bot, NOT_SAMPLED)
    b.say("what is etumba")
    b.say("thanks")
    assert not _asked(b)
    _run(b, CALLBACK)
    assert not _asked(b)
    _run(b, COMPLAINT)
    assert not _asked(b)
    assert not _events("csat_asked")


@pytest.mark.parametrize("steps,resolved", [(CALLBACK, "callback"), (COMPLAINT, "complaint")])
def test_asked_when_a_callback_or_complaint_finishes(bot, rate, steps, resolved):
    b = _run(_customer(bot), steps)
    assert _asked(b)
    assert b.session.slots["csat_asked"] == resolved
    assert b.buttons == [CSAT_UP, CSAT_DOWN, "menu"]
    assert "reference" in b.last[0][0]["text"].lower()  # the ticket reply comes first


def test_thanks_as_the_first_message_is_not_resolved(bot, rate):
    rate(1)
    b = bot()
    b.say("thanks")
    assert b.last[1].get("intent") == "thanks_goodbye"
    assert not _asked(b)


def test_no_csat_after_a_fraud_report(bot, rate):
    rate(1)
    b = _run(bot(), FRAUD)
    assert b.session.active_flow is None and "FRD-" in b.text
    assert not _asked(b)
    b.say("thanks")
    assert not _asked(b)
    _run(b, CALLBACK)  # nor later in the same session
    assert not _asked(b)
    assert not _events("csat_asked")


def test_a_cancelled_callback_is_not_resolved(bot, rate):
    rate(1)
    b = _run(bot(), CALLBACK[:3])
    b.tap("cancel_flow")
    assert not _asked(b)


def test_internal_markers_never_leave_the_router(bot, rate):
    rate(1)
    b = _run(bot(), CALLBACK)
    for reply in b.last[0]:
        assert set(reply) <= {"text", "buttons"}, reply


# --- the tap ---------------------------------------------------------------------


@pytest.mark.parametrize("channel", ["web", "whatsapp", "messenger"])
def test_tap_is_logged_with_its_channel(bot, rate, channel):
    b = _customer(bot, channel=channel)
    b.say("what is etumba")
    b.say("thanks")
    b.tap(CSAT_UP)
    assert b.action == "csat:up"
    assert b.buttons == [m["payload"] for m in MENU_BUTTONS]  # the menu stays
    rows = [r for r in _events("csat:up") if r[0] == "bot"]
    assert len(rows) == 1 and rows[0][1] == channel and rows[0][2] == SAMPLED


def test_thumbs_down_offers_a_person_first(bot, rate):
    b = _customer(bot)
    b.say("what is etumba")
    b.say("thanks")
    b.tap(CSAT_DOWN)
    assert b.action == "csat:down"
    assert b.buttons[0] == "human_handoff"
    assert set(b.buttons) == {m["payload"] for m in MENU_BUTTONS}
    assert "talk to a person" in b.text.lower()


def test_only_the_first_tap_counts(bot, rate):
    b = _customer(bot)
    b.say("what is etumba")
    b.say("thanks")
    b.tap(CSAT_UP)
    b.tap(CSAT_DOWN)  # an old button tapped again
    assert b.action == "csat_ignored"
    assert len(_events("csat:up")) == 1 and not _events("csat:down")


def test_an_unasked_tap_is_not_counted(bot, rate):
    b = _customer(bot, NOT_SAMPLED)
    b.tap(CSAT_UP)
    assert b.action == "csat_ignored"
    assert b.buttons  # thanked, never a dead end
    assert not _events("csat:up")


def test_stale_tap_mid_flow_is_never_stored_as_an_answer(bot, rate):
    b = _customer(bot)
    b.say("what is etumba")
    b.say("thanks")
    b.tap("human_handoff")  # now at the callback's name step
    b.tap(CSAT_DOWN)
    assert b.action == "csat:down"
    assert b.session.active_flow == "lead"
    assert "name" not in b.session.flow_state["data"]
    assert "what's your name" in b.text.lower()
    assert b.buttons[0] == "human_handoff"
    b.say("Mary")
    assert b.session.flow_state["data"]["name"] == "Mary"


# --- typed answers after the question ------------------------------------------------


def test_typed_no_still_answers_anything_else(bot, rate):
    b = _run(_customer(bot), CALLBACK)
    assert _asked(b)
    b.say("no")
    assert b.last[1].get("intent") == "thanks_goodbye"
    assert not _asked(b)  # once per session


def test_typed_number_picks_a_thumb(bot, rate):
    b = _run(_customer(bot), CALLBACK)
    b.say("1")
    assert b.action == "csat:up"


# --- channels ------------------------------------------------------------------------


def test_whatsapp_gets_one_bubble_with_three_reply_buttons(bot, rate):
    b = _run(_customer(bot, channel="whatsapp"), CALLBACK)
    (reply,) = b.last[0]  # P5: merged, one billable message
    assert "reference" in reply["text"].lower() and "tell us how I did" in reply["text"]
    (message,) = render.whatsapp(reply)
    assert message["interactive"]["type"] == "button"  # one tap, not a list
    ids = [x["reply"]["id"] for x in message["interactive"]["action"]["buttons"]]
    assert ids == [CSAT_UP, CSAT_DOWN, "menu"]


def test_web_keeps_the_ticket_reply_and_the_question_apart(bot, rate):
    b = _run(_customer(bot), CALLBACK)
    assert len(b.last[0]) == 2
    assert b.last[0][0]["buttons"]  # the finish reply keeps its own buttons


def test_whatsapp_webhook_round_trip(meta_env, monkeypatch):
    from test_whatsapp import RAW_NUMBER, payload, say

    monkeypatch.setenv("CSAT_SAMPLE_RATE", "1")
    say(meta_env, "what is etumba")
    say(meta_env, "thanks")
    last = meta_env.outbox("whatsapp")[-1]
    assert last["interactive"]["type"] == "button"
    assert [b["reply"]["id"] for b in last["interactive"]["action"]["buttons"]] == [CSAT_UP, CSAT_DOWN, "menu"]
    body = payload("button_reply")
    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    message["interactive"]["button_reply"]["id"] = CSAT_DOWN
    message["id"] = "wamid.CSAT"
    meta_env.post("whatsapp", body)
    meta_env.process()
    rows = [r for r in _events("csat:down") if r[0] == "bot"]
    assert len(rows) == 1 and rows[0][1] == "whatsapp"
    assert rows[0][2] and RAW_NUMBER not in rows[0][2]  # hashed, never the number
    assert "Talk to a person" in json.dumps(meta_env.outbox("whatsapp")[-1])


def test_widget_endpoint_carries_the_question(client, monkeypatch, isolated_data):
    from conftest import chat

    from app.session import store

    monkeypatch.setenv("CSAT_SAMPLE_RATE", "1")
    sid = chat(client)["session_id"]
    chat(client, sid, message="what is etumba")
    data = chat(client, sid, message="thanks")
    assert data["meta"].get("csat") == "asked"
    assert [b["payload"] for b in data["replies"][-1]["buttons"]] == [CSAT_UP, CSAT_DOWN, "menu"]
    data = chat(client, sid, payload=CSAT_UP)
    assert data["meta"]["action"] == "csat:up"
    with store.web_session(sid) as (session, _):
        assert session.slots["csat_answered"] == CSAT_UP


def test_thanks_followed_by_a_new_question_is_not_resolved(bot, rate):
    # C10 answers both halves in one reply; the customer has just asked
    # something new, so nothing is resolved yet.
    rate(1)
    b = bot()
    b.say("what is etumba")
    b.say("thank you so much and what are your opening hours")
    assert b.last[1].get("intents") == ["thanks_goodbye", "opening_hours"]
    assert not _asked(b)
    assert CSAT_UP not in b.buttons

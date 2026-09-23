"""End-to-end flow tests through POST /chat (acceptance §3.5)."""

import re
import sqlite3

import pytest
from conftest import chat

from app import audit
from app.router import matcher


def new_session(client):
    data = chat(client)
    assert "automated" in data["replies"][0]["text"].lower()  # disclosure (§3.4)
    return data["session_id"]


def _all_text(data):
    return " ".join(r["text"] for r in data["replies"])


def test_welcome_discloses_and_offers_menu(client):
    data = chat(client)
    text = data["replies"][0]["text"].lower()
    assert "automated" in text and "not a person" in text
    buttons = data["replies"][-1]["buttons"]
    assert any(b["payload"] == "human_handoff" for b in buttons)


def test_fraud_urgent_fires_mid_conversation_with_transcript(client):
    sid = new_session(client)
    chat(client, sid, message="what is etumba")
    data = chat(client, sid, message="I think I've been scammed, money is missing")
    assert data["meta"]["action"] == "urgent:fraud"
    assert "urgent" in _all_text(data).lower() or "call" in _all_text(data).lower()

    chat(client, sid, message="Someone called pretending to be the bank")
    chat(client, sid, message="today")
    chat(client, sid, message="eTumba")
    chat(client, sid, message="0977123456")
    data = chat(client, sid, payload="confirm_yes")
    match = re.search(r"FRD-\d{8}-[A-Z0-9]{4}", _all_text(data))
    assert match, _all_text(data)
    # never bot-resolved: ticket open, transcript attached (§1 rules 3 & 7)
    con = sqlite3.connect(audit.DB_FILE)
    row = con.execute(
        "SELECT status, transcript FROM tickets WHERE ref = ?", (match.group(0),)
    ).fetchone()
    con.close()
    assert row is not None
    assert row[0] == "open"
    assert "etumba" in row[1].lower()


def test_lost_card_urgent_route(client):
    sid = new_session(client)
    data = chat(client, sid, message="i lost my card")
    assert data["meta"]["action"] == "urgent:fraud"
    assert "block" in _all_text(data).lower()


def test_complaint_flow_returns_reference(client):
    sid = new_session(client)
    data = chat(client, sid, message="I want to complain")
    assert data["meta"]["action"] == "urgent:complaint"
    chat(client, sid, message="Service at a branch")
    chat(client, sid, message="I waited two hours and nobody helped me")
    chat(client, sid, message="skip")
    data = chat(client, sid, payload="confirm_yes")
    assert re.search(r"CMP-\d{8}-[A-Z0-9]{4}", _all_text(data))


def test_callback_flow_promises_one_working_day(client):
    sid = new_session(client)
    chat(client, sid, payload="human_handoff")
    chat(client, sid, message="Choolwe")
    chat(client, sid, message="0977123456")
    chat(client, sid, message="Opening a business account")
    chat(client, sid, payload="Morning")
    data = chat(client, sid, payload="confirm_yes")
    text = _all_text(data)
    assert "one working day" in text
    assert re.search(r"CBK-\d{8}-[A-Z0-9]{4}", text)
    # the closing question gets an explicit, unambiguous button
    assert any(b["payload"] == "thanks_goodbye" for b in data["replies"][-1]["buttons"])


def test_callback_flow_rejects_invalid_phone_and_reprompts(client):
    sid = new_session(client)
    chat(client, sid, payload="human_handoff")
    chat(client, sid, message="Choolwe")
    data = chat(client, sid, message="12345")  # not a Zambian number
    assert "doesn't look like a valid number" in _all_text(data)
    # still on the phone step — a valid number now must be accepted
    data = chat(client, sid, message="0977123456")
    assert "what would you like to discuss" in _all_text(data).lower()


@pytest.mark.parametrize(
    "phone",
    ["0977123456", "260977123456", "+260977123456", "0977 123 456", "0977-123-456"],
)
def test_callback_flow_accepts_valid_phone_formats(client, phone):
    sid = new_session(client)
    chat(client, sid, payload="human_handoff")
    chat(client, sid, message="Choolwe")
    data = chat(client, sid, message=phone)
    assert "what would you like to discuss" in _all_text(data).lower()


def test_saying_no_after_callback_is_recognised_as_goodbye(client):
    sid = new_session(client)
    chat(client, sid, payload="human_handoff")
    chat(client, sid, message="Choolwe")
    chat(client, sid, message="0977123456")
    chat(client, sid, message="Opening a business account")
    chat(client, sid, payload="Morning")
    chat(client, sid, payload="confirm_yes")
    data = chat(client, sid, message="no")
    assert data["meta"]["action"] == "answer"
    assert data["meta"]["intent"] == "thanks_goodbye"
    assert "welcome" in _all_text(data).lower()


def test_two_strike_rule_offers_human(client):
    sid = new_session(client)
    first = chat(client, sid, message="flurb zzqx vortblatt")
    assert first["meta"]["action"] == "fallback"
    second = chat(client, sid, message="wibble vortz maximally")
    assert second["meta"]["action"] == "two_strike"
    buttons = second["replies"][-1]["buttons"]
    assert any(b["payload"] == "human_handoff" for b in buttons)


def test_did_you_mean_on_medium_confidence(client):
    sid = new_session(client)
    # generic single word: should suggest, not guess (or answer confidently)
    data = chat(client, sid, message="account")
    assert data["meta"]["action"] in ("did_you_mean", "answer")
    assert data["replies"][-1]["buttons"]


def test_no_dead_ends_for_every_intent(client):
    # Automated check for §3.5: every response contains at least one action.
    for name in matcher.intents:
        sid = chat(client)["session_id"]
        data = chat(client, sid, payload=name)
        assert data["replies"][-1]["buttons"], f"dead end after payload {name}"


def test_pii_never_reaches_logs_or_replies(client):
    card = "5454 1212 3434 5656"
    sid = new_session(client)
    data = chat(client, sid, message=f"my card number is {card} can you help")
    assert "never need them" in _all_text(data)
    assert card not in _all_text(data)
    jsonl = (audit.JSONL_FILE).read_text(encoding="utf-8")
    assert "5454 1212" not in jsonl
    con = sqlite3.connect(audit.DB_FILE)
    hits = con.execute(
        "SELECT COUNT(*) FROM events WHERE text LIKE ?", (f"%5454 1212%",)
    ).fetchone()[0]
    con.close()
    assert hits == 0


def test_fraud_flow_captures_a_callback_number(client):
    """Regression test for a real gap found reviewing external banking-bot
    repos: the fraud flow used to finish() with no contact info at all, so
    "a member of staff will contact you" had no channel to actually do that."""
    sid = new_session(client)
    chat(client, sid, message="i think i was scammed")
    chat(client, sid, message="Someone called pretending to be the bank")
    chat(client, sid, message="today")
    chat(client, sid, message="eTumba")
    data = chat(client, sid, message="not a phone number")
    assert "doesn't look like a valid number" in _all_text(data)
    chat(client, sid, message="0977123456")
    data = chat(client, sid, payload="confirm_yes")
    match = re.search(r"FRD-\d{8}-[A-Z0-9]{4}", _all_text(data))
    assert match, _all_text(data)
    con = sqlite3.connect(audit.DB_FILE)
    fields = con.execute(
        "SELECT fields FROM tickets WHERE ref = ?", (match.group(0),)
    ).fetchone()[0]
    con.close()
    assert "0977123456" in fields


def test_confirm_step_shows_summary_and_allows_edit(client):
    sid = new_session(client)
    chat(client, sid, message="I want to complain")
    chat(client, sid, message="Service at a branch")
    chat(client, sid, message="I waited two hours and nobody helped me")
    data = chat(client, sid, message="skip")
    summary_text = _all_text(data)
    assert "waited two hours" in summary_text
    assert any(b["payload"] == "confirm_yes" for b in data["replies"][-1]["buttons"])
    assert any(b["payload"] == "confirm_edit" for b in data["replies"][-1]["buttons"])

    # Editing goes back to the last field instead of submitting.
    data = chat(client, sid, payload="confirm_edit")
    assert "best phone number or email" in _all_text(data).lower()
    data = chat(client, sid, message="skip")
    assert any(b["payload"] == "confirm_yes" for b in data["replies"][-1]["buttons"])

    data = chat(client, sid, payload="confirm_yes")
    assert re.search(r"CMP-\d{8}-[A-Z0-9]{4}", _all_text(data))


def test_faq_question_mid_flow_is_answered_and_flow_resumes(client):
    """§ pattern borrowed from RasaHQ/financial-demo: a high-confidence,
    unrelated FAQ question asked mid-flow gets answered without losing the
    customer's progress, instead of the flow trying to treat it as an
    answer to the current field. Only fraud's "what_happened" and
    complaint's "details" opt into this (see interruptible_fields) — a
    fraud/complaint narrative is unlikely to itself resemble an FAQ
    question, unlike e.g. fraud's "channel" field, whose legitimate answers
    (card, eTumba, branch) collide with real FAQ topics."""
    sid = new_session(client)
    chat(client, sid, message="i think i was scammed")  # fraud flow, step: what_happened
    data = chat(client, sid, message="what is etumba")
    text = _all_text(data)
    assert "mobile wallet" in text.lower() or "e-tumba" in text.lower() or "etumba" in text.lower()
    assert "back to your fraud report" in text.lower()
    assert "please tell me briefly what happened" in text.lower()
    # The flow is still active and un-advanced: a real answer now proceeds normally.
    data = chat(client, sid, message="Someone called pretending to be the bank")
    assert "when did this happen" in _all_text(data).lower()


def test_locator_flow_finds_placeholder_branch(client):
    sid = new_session(client)
    chat(client, sid, payload="branch_locator")
    data = chat(client, sid, message="Lusaka")
    assert "Lusaka" in _all_text(data)
    assert data["replies"][-1]["buttons"]


def test_kill_switch_free_text(client, monkeypatch):
    monkeypatch.setenv("FREE_TEXT_ENABLED", "0")
    sid = new_session(client)
    data = chat(client, sid, message="savings account")
    assert data["meta"]["action"] == "freetext_off"
    assert data["replies"][-1]["buttons"]  # menu still works
    data = chat(client, sid, payload="savings_account")
    assert data["meta"]["action"] == "answer"


def test_kill_switch_widget(client, monkeypatch):
    monkeypatch.setenv("WIDGET_ENABLED", "0")
    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 503
    health = client.get("/health").json()
    assert health["widget_enabled"] is False


def test_talk_to_person_works_even_mid_flow(client):
    sid = new_session(client)
    chat(client, sid, payload="branch_locator")  # locator flow active
    data = chat(client, sid, payload="human_handoff")
    assert data["meta"]["action"] == "flow_start"
    assert "name" in _all_text(data).lower()


# --- Page-reload resume: a refresh must never wipe an in-progress flow ---


def test_empty_post_on_new_session_still_welcomes(client):
    data = chat(client)
    assert data["meta"]["action"] == "welcome"
    assert data["history"] == []


def test_refresh_mid_fraud_flow_resumes_not_wipes(client):
    sid = new_session(client)
    data = chat(client, sid, message="i lost my card")
    assert data["meta"]["action"] == "urgent:fraud"
    chat(client, sid, message="Lost it at the market")  # step: what_happened
    # Customer refreshes the page — the widget reopens with an empty post.
    data = chat(client, sid)
    assert data["meta"]["action"] == "resume_flow"
    assert "pick up where we left off" in _all_text(data).lower()
    # The flow continues from the same step and the pre-refresh answer survives.
    chat(client, sid, message="today")
    chat(client, sid, message="card")
    chat(client, sid, message="0977123456")
    data = chat(client, sid, payload="confirm_yes")
    match = re.search(r"FRD-\d{8}-[A-Z0-9]{4}", _all_text(data))
    assert match, _all_text(data)
    con = sqlite3.connect(audit.DB_FILE)
    fields = con.execute(
        "SELECT fields FROM tickets WHERE ref = ?", (match.group(0),)
    ).fetchone()[0]
    con.close()
    assert "market" in fields.lower()


def test_refresh_mid_locator_flow_reprompts_city(client):
    sid = new_session(client)
    chat(client, sid, payload="branch_locator")
    data = chat(client, sid)  # page reload
    assert data["meta"]["action"] == "resume_flow"
    assert "which town or city" in _all_text(data).lower()
    data = chat(client, sid, message="Lusaka")
    assert "Lusaka" in _all_text(data)


def test_resume_replays_masked_history_without_button_payloads(client):
    sid = new_session(client)
    chat(client, sid, message="what is etumba")
    chat(client, sid, payload="menu")
    data = chat(client, sid)  # page reload, no active flow
    assert data["meta"]["action"] == "resume"
    history = data["history"]
    assert any(t["role"] == "user" and "etumba" in t["text"].lower() for t in history)
    # internal '[button] <payload>' turns are never shown to the customer
    assert not any(t["text"].startswith("[button]") for t in history)


# --- S2: every fraud ticket carries a contact, or an explicit "skipped" ---


def _fraud_to_contact_step(b):
    b.say("i think i was scammed")
    b.say("Someone called pretending to be the bank")
    b.say("today")
    b.say("eTumba")


def _ticket_fields(ref):
    import json

    con = sqlite3.connect(audit.DB_FILE)
    fields = con.execute("SELECT fields FROM tickets WHERE ref = ?", (ref,)).fetchone()[0]
    con.close()
    return json.loads(fields)


def _ref(text):
    match = re.search(r"FRD-\d{8}-[A-Z0-9]{4}", text)
    assert match, text
    return match.group(0)


def test_fraud_contact_is_read_back_formatted(bot):
    b = bot()
    _fraud_to_contact_step(b)
    b.say("12345")  # rejected first
    b.say("260 977 123 456")
    assert "Got it: 0977 123 456." in b.text
    b.tap("confirm_yes")
    assert _ticket_fields(_ref(b.text))["contact"] == "260977123456"


def test_fraud_contact_accepts_email(bot):
    b = bot()
    _fraud_to_contact_step(b)
    b.say("mary.banda@example.com")
    assert "Got it: mary.banda@example.com." in b.text
    b.tap("confirm_yes")
    assert _ticket_fields(_ref(b.text))["contact"] == "mary.banda@example.com"


def test_fraud_contact_skip_states_the_consequence(bot):
    b = bot()
    _fraud_to_contact_step(b)
    b.say("skip")
    assert "can't call you back" in b.text
    assert "888" in b.text  # {contact_phone} rendered
    b.tap("confirm_yes")
    assert _ticket_fields(_ref(b.text))["contact"] == "skipped"

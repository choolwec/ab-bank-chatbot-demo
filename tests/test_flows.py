"""End-to-end flow tests through POST /chat (acceptance §3.5)."""

import re
import sqlite3

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
    data = chat(client, sid, message="eTumba")
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
    data = chat(client, sid, message="skip")
    assert re.search(r"CMP-\d{8}-[A-Z0-9]{4}", _all_text(data))


def test_callback_flow_promises_one_working_day(client):
    sid = new_session(client)
    chat(client, sid, payload="human_handoff")
    chat(client, sid, message="Choolwe")
    chat(client, sid, message="0977123456")
    chat(client, sid, message="Opening a business account")
    data = chat(client, sid, payload="Morning")
    text = _all_text(data)
    assert "one working day" in text
    assert re.search(r"CBK-\d{8}-[A-Z0-9]{4}", text)


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
    data = chat(client, sid, message="card")
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

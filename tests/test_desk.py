"""H2: the Chatwoot agent desk, round trip against a fake Chatwoot
(httpx.MockTransport). WhatsApp runs in its mock mode (data/whatsapp_outbox_mock.jsonl)."""

import json
import re
import sqlite3
import time
from pathlib import Path

import httpx
import pytest

from app import audit, config
from app.desk import bridge, chatwoot
from app.identity import user_hash

WA = Path(__file__).parent / "data" / "wa"
RAW_NUMBER = "260977123456"
RAW_FORMS = (RAW_NUMBER, "0977123456", "0977 123 456", "977123456")
SECRET = "desk-webhook-secret-0123456789abcdef"
KEY = f"whatsapp:{user_hash(f'whatsapp:{RAW_NUMBER}')}"


class FakeChatwoot:
    """Just enough of the Application API: contacts, conversations, messages."""

    BASE = "/api/v1/accounts/1"

    def __init__(self):
        self.requests = []
        self.contacts = []
        self.conversations = {}
        self.messages = {}
        self.fail = {}  # path suffix -> HTTP status to answer with

    def handler(self, request):
        body = json.loads(request.content) if request.content else None
        self.requests.append({"method": request.method, "url": str(request.url), "json": body,
                              "token": request.headers.get("api_access_token")})
        assert request.url.path.startswith(self.BASE), request.url
        rest = request.url.path[len(self.BASE):]
        if rest in self.fail:
            return httpx.Response(self.fail[rest], json={})
        if request.method == "GET" and rest == "/contacts/search":
            q = request.url.params["q"]
            return httpx.Response(200, json={"meta": {}, "payload": [c for c in self.contacts if q in c["identifier"]]})
        if request.method == "POST" and rest == "/contacts":
            contact = dict(body, id=100 + len(self.contacts))
            self.contacts.append(contact)
            return httpx.Response(200, json={"payload": {"contact": contact, "contact_inbox": {"source_id": "x"}}})
        if request.method == "POST" and rest == "/conversations":
            conv = 7 + len(self.conversations)
            self.conversations[conv] = body
            return httpx.Response(200, json={"id": conv, "account_id": 1, "inbox_id": 5})
        m = re.fullmatch(r"/conversations/(\d+)/messages", rest)
        if m and request.method == "POST":
            self.messages.setdefault(int(m.group(1)), []).append(body)
            return httpx.Response(200, json=dict(body, id=len(self.requests)))
        return httpx.Response(404, json={})

    def posted(self, conv, **match):
        return [m for m in self.messages.get(conv, []) if all(m.get(k) == v for k, v in match.items())]

    def wire(self) -> str:
        """Everything that went over the wire to Chatwoot, as one string."""
        return json.dumps(self.requests, ensure_ascii=False)


def _configure(monkeypatch, secret=SECRET):
    monkeypatch.setenv("CHATWOOT_URL", "https://desk.example.test")
    monkeypatch.setenv("CHATWOOT_ACCOUNT_ID", "1")
    monkeypatch.setenv("CHATWOOT_INBOX_ID", "5")
    monkeypatch.setenv("CHATWOOT_API_TOKEN", "cw-token")
    monkeypatch.setenv("CHATWOOT_WEBHOOK_SECRET", secret)


@pytest.fixture
def fake(monkeypatch):
    fake = FakeChatwoot()
    monkeypatch.setattr(chatwoot, "client", chatwoot.ChatwootClient(
        transport=httpx.MockTransport(fake.handler), sleep=lambda s: None))
    monkeypatch.setenv("JIRA_ENABLED", "true")  # mock mode: gives the ticket a Jira key
    return fake


@pytest.fixture
def desk(meta_env, fake, monkeypatch):
    _configure(monkeypatch)
    return fake


def wa(meta_env, text=None, button=None, ts=None):
    """One WhatsApp message from the customer, through the webhook and worker."""
    name = "button_reply" if button else "text"
    raw = (WA / f"{name}.json").read_text(encoding="utf-8").replace("TS", str(int(ts or time.time())))
    body = json.loads(raw)
    m = body["entry"][0]["changes"][0]["value"]["messages"][0]
    m["id"] = f"wamid.{time.time_ns()}"
    if button:
        m["interactive"]["button_reply"]["id"] = button
    else:
        m["text"] = {"body": text}
    assert meta_env.post("whatsapp", body).status_code == 200
    meta_env.process()


def handoff(meta_env):
    wa(meta_env, "hello")
    wa(meta_env, button="human_handoff")


def session_state(meta_env):
    with meta_env.store.session(KEY, "whatsapp") as (session, created):
        assert not created
        return session


def hook(meta_env, body, secret=SECRET):
    return meta_env.client.post(f"/webhooks/chatwoot/{secret}", json=body)


def agent_says(meta_env, text, conv=7, **extra):
    body = {"event": "message_created", "message_type": "outgoing", "private": False,
            "content_type": "text", "content": text, "conversation": {"id": conv},
            "sender": {"id": 3, "type": "user"}}
    body.update(extra)
    assert hook(meta_env, body).status_code == 200


def events(action):
    return [json.loads(line) for line in audit.JSONL_FILE.read_text(encoding="utf-8").splitlines()
            if json.loads(line)["action"] == action]


# --- handoff -------------------------------------------------------------------------------


def test_handoff_creates_contact_conversation_and_private_note(meta_env, desk):
    handoff(meta_env)
    session = session_state(meta_env)
    ref, jira_key = sqlite3.connect(audit.DB_FILE).execute(
        "SELECT ref, jira_key FROM tickets WHERE type = 'handoff'").fetchone()
    assert jira_key  # the Jira (mock) issue is linked on our ticket

    (contact,) = desk.contacts
    assert contact["identifier"] == session.user_hash and "name" not in contact
    conv = desk.conversations[7]
    assert conv["inbox_id"] == 5 and conv["contact_id"] == contact["id"] and conv["status"] == "open"
    assert conv["custom_attributes"] == {"ticket_ref": ref, "jira_key": jira_key, "channel": "whatsapp"}
    (note,) = desk.posted(7, private=True)
    assert note["message_type"] == "outgoing"
    assert ref in note["content"] and jira_key in note["content"]
    assert "[user] hello" in note["content"] and "/admin/cases" in note["content"]
    assert all(r["token"] == "cw-token" for r in desk.requests)

    assert session.slots[bridge.CONVERSATION_SLOT] == 7
    assert session.bot_paused_until > time.time() + 23 * 3600
    assert "a person will reply to you right here" in meta_env.sent_texts("whatsapp")[-1]
    assert events("desk_handoff")


def test_a_customer_message_while_paused_is_forwarded_masked(meta_env, desk):
    handoff(meta_env)
    before = len(meta_env.sent_texts("whatsapp"))
    wa(meta_env, "my card is 4111 1111 1111 1111, call me on 0966 555 444")
    (forwarded,) = desk.posted(7, message_type="incoming")
    assert forwarded["private"] is False
    assert "[CARD REDACTED]" in forwarded["content"] and bridge.PHONE_MASK in forwarded["content"]
    assert "4111" not in forwarded["content"] and "555 444" not in forwarded["content"]
    assert len(meta_env.sent_texts("whatsapp")) == before  # the bot stays quiet
    assert events("paused")  # still logged, as before H2


def test_customer_messages_do_not_extend_the_pause(meta_env, desk):
    handoff(meta_env)
    until = session_state(meta_env).bot_paused_until
    wa(meta_env, "hello? anyone there?")
    assert session_state(meta_env).bot_paused_until == until


# --- agent replies ---------------------------------------------------------------------------


def test_an_agent_reply_is_delivered_on_whatsapp(meta_env, desk):
    handoff(meta_env)
    agent_says(meta_env, "Hello, this is Mary from the contact centre. How can I help?")
    last = meta_env.outbox("whatsapp")[-1]
    assert last["type"] == "text" and last["text"]["body"].startswith("Hello, this is Mary")
    assert last["to"] == f"hash:{user_hash(f'whatsapp:{RAW_NUMBER}')}"  # the mock records a hash
    (reply,) = events("desk_agent_reply")
    assert reply["role"] == "agent" and RAW_NUMBER not in json.dumps(reply)
    assert session_state(meta_env).transcript[-1]["role"] == "agent"


def test_an_agent_reply_extends_the_pause(meta_env, desk):
    handoff(meta_env)
    with meta_env.store.session(KEY, "whatsapp") as (session, _):
        session.bot_paused_until = time.time() + 60
    agent_says(meta_env, "Still looking into it.")
    assert session_state(meta_env).bot_paused_until > time.time() + 23 * 3600


def test_private_notes_incoming_and_non_text_messages_are_not_sent(meta_env, desk):
    handoff(meta_env)
    before = len(meta_env.outbox("whatsapp"))
    agent_says(meta_env, "internal: check the Jira ticket", private=True)
    agent_says(meta_env, "a forwarded customer message", message_type="incoming")
    agent_says(meta_env, "Rate us", content_type="input_csat")
    agent_says(meta_env, "Conversation was resolved", message_type="activity")
    assert len(meta_env.outbox("whatsapp")) == before


def test_an_agent_reply_after_24_hours_is_refused_with_a_note(meta_env, desk):
    handoff(meta_env)
    with meta_env.store.session(KEY, "whatsapp") as (session, _):
        session.last_inbound_at = time.time() - 25 * 3600
    before = len(meta_env.outbox("whatsapp"))
    agent_says(meta_env, "Sorry for the wait, are you still there?")
    assert len(meta_env.outbox("whatsapp")) == before  # nothing sent
    note = desk.posted(7, private=True)[-1]["content"]
    assert "case_update" in note and "/admin/cases" in note
    assert events("desk_window_closed")


def test_an_attachment_only_reply_gets_a_note(meta_env, desk):
    handoff(meta_env)
    before = len(meta_env.outbox("whatsapp"))
    agent_says(meta_env, "", attachments=[{"file_type": "image"}])
    assert len(meta_env.outbox("whatsapp")) == before
    assert "Attachments are not sent" in desk.posted(7, private=True)[-1]["content"]


def test_a_reply_on_an_unknown_conversation_gets_a_note(meta_env, desk):
    agent_says(meta_env, "Hello?", conv=999)
    assert "no longer linked" in desk.posted(999, private=True)[-1]["content"]
    assert meta_env.outbox("whatsapp") == []


# --- resuming the bot ------------------------------------------------------------------------


def test_resolving_the_conversation_resumes_the_bot(meta_env, desk):
    handoff(meta_env)
    hook(meta_env, {"event": "conversation_status_changed", "id": 7, "status": "snoozed"})
    assert session_state(meta_env).bot_paused_until > time.time()
    hook(meta_env, {"event": "conversation_status_changed", "id": 7, "status": "resolved"})
    session = session_state(meta_env)
    assert session.bot_paused_until == 0 and bridge.CONVERSATION_SLOT not in session.slots
    wa(meta_env, "what is etumba")
    assert "mobile wallet" in meta_env.sent_texts("whatsapp")[-1]
    assert not desk.posted(7, message_type="incoming")  # no longer forwarded
    assert events("desk_resolved")


def test_idle_fallback_unpauses_after_24_hours(meta_env, desk):
    handoff(meta_env)
    with meta_env.store.session(KEY, "whatsapp") as (session, _):
        session.bot_paused_until = time.time() - 1  # DESK_IDLE_HOURS without an agent reply
    wa(meta_env, "what is etumba")
    assert "mobile wallet" in meta_env.sent_texts("whatsapp")[-1]
    note = desk.posted(7, private=True)[-1]["content"]
    assert f"No agent reply for {config.DESK_IDLE_HOURS} hours" in note
    assert bridge.CONVERSATION_SLOT not in session_state(meta_env).slots
    assert events("desk_idle_resume")


def test_a_second_handoff_reuses_the_contact(meta_env, desk):
    handoff(meta_env)
    hook(meta_env, {"event": "conversation_status_changed", "id": 7, "status": "resolved"})
    wa(meta_env, button="human_handoff")
    assert len(desk.contacts) == 1 and set(desk.conversations) == {7, 8}
    assert session_state(meta_env).slots[bridge.CONVERSATION_SLOT] == 8
    # resolving the OLD conversation doesn't unpause the new one
    hook(meta_env, {"event": "conversation_status_changed", "id": 7, "status": "resolved"})
    assert session_state(meta_env).bot_paused_until > time.time()


# --- the webhook's door -----------------------------------------------------------------------


def test_a_bad_secret_gets_403_and_changes_nothing(meta_env, desk):
    handoff(meta_env)
    before = len(meta_env.outbox("whatsapp"))
    body = {"event": "message_created", "message_type": "outgoing", "private": False,
            "content": "hi", "conversation": {"id": 7}}
    assert hook(meta_env, body, secret="wrong-secret-wrong-secret-wrong").status_code == 403
    assert hook(meta_env, {"event": "conversation_status_changed", "id": 7, "status": "resolved"},
                secret=SECRET[:-1]).status_code == 403
    assert len(meta_env.outbox("whatsapp")) == before
    assert session_state(meta_env).bot_paused_until > time.time()


def test_a_short_or_missing_secret_means_no_webhook(meta_env, fake, monkeypatch):
    _configure(monkeypatch, secret="short")
    assert hook(meta_env, {"event": "x"}, secret="short").status_code == 404
    monkeypatch.delenv("CHATWOOT_WEBHOOK_SECRET")
    assert hook(meta_env, {"event": "x"}, secret="anything").status_code == 404


def test_a_malformed_body_is_acknowledged(meta_env, desk):
    r = meta_env.client.post(f"/webhooks/chatwoot/{SECRET}", content=b"not json",
                             headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    assert bridge.handle_event({"event": "contact_created"}) == "ignored"


# --- privacy ----------------------------------------------------------------------------------


def test_no_raw_phone_number_or_wa_id_reaches_chatwoot(meta_env, desk):
    wa(meta_env, "i think i was scammed")
    wa(meta_env, "they called pretending to be the bank")
    wa(meta_env, "yesterday")
    wa(meta_env, "eTumba")
    wa(meta_env, "0977 123 456")  # the customer types their own WhatsApp number
    wa(meta_env, button="human_handoff")
    wa(meta_env, "my number is +260977123456, pin is 4321")
    agent_says(meta_env, "Thanks, we are checking.")
    wire = desk.wire()
    assert desk.requests and "[user] i think i was scammed" in desk.posted(7, private=True)[0]["content"]
    for form in RAW_FORMS:
        assert form not in wire, form
    assert "4321" not in wire
    session = session_state(meta_env)
    assert desk.contacts[0]["identifier"] == session.user_hash
    assert (meta_env.tmp / "desk.db").exists()
    assert RAW_NUMBER.encode() not in (meta_env.tmp / "desk.db").read_bytes()


def test_desk_text_redacts_phone_numbers_but_not_references_or_amounts():
    assert bridge.desk_text("call 0977 123 456 or +260966123456") == (
        f"call {bridge.PHONE_MASK} or {bridge.PHONE_MASK}")
    assert bridge.desk_text("0977123456 0966123456") == f"{bridge.PHONE_MASK} {bridge.PHONE_MASK}"
    for kept in ("my case is FRD-20260924-1234", "ZMW 1,250,000.00", "paid 1 250 000 on 24/09/2026",
                 "HND-20260924-AB12, Jira CC-17"):
        assert bridge.desk_text(kept) == kept
    assert "[CARD REDACTED]" in bridge.desk_text("card 4111 1111 1111 1111")
    for written in ("(0977) 123456", "0977.123.456", "0977/123/456", "+260 (97) 7123456"):
        assert bridge.desk_text(f"call me on {written} please") == f"call me on {bridge.PHONE_MASK} please"
    for kept in ("on 01/10/2026 10:30", "on 01.10.2026 10:30", "K 0.50"):
        assert bridge.desk_text(kept) == kept


def test_desk_text_redacts_email_addresses():
    for written in ("mary.banda@example.com", "M.Banda+bank@mail.example.co.zm", "x_y-z@abc-bank.zm"):
        assert bridge.desk_text(f"email me at {written} please") == f"email me at {bridge.EMAIL_MASK} please"
    for kept in ("FRD-20260924-1234", "support at the branch", "@abbank on Facebook", "a@b"):
        assert bridge.desk_text(kept) == kept


def test_a_fraud_contact_email_reaches_the_ticket_but_never_chatwoot(meta_env, desk):
    email = "mary.banda@example.com"
    wa(meta_env, "i think i was scammed")
    wa(meta_env, "they called pretending to be the bank")
    wa(meta_env, "yesterday")
    wa(meta_env, "eTumba")
    wa(meta_env, email)  # the fraud report's contact step
    wa(meta_env, button="human_handoff")
    wa(meta_env, f"or write to {email.upper()}")  # forwarded while paused
    wire = desk.wire()
    assert desk.posted(7, private=True) and desk.posted(7, message_type="incoming")
    assert email not in wire.lower() and "example.com" not in wire.lower()
    assert bridge.EMAIL_MASK in wire
    # Staff keep the customer's chosen contact channel on the ticket (and Jira).
    (fields,) = sqlite3.connect(audit.DB_FILE).execute(
        "SELECT fields FROM tickets WHERE type = 'fraud'").fetchone()
    assert json.loads(fields)["contact"] == email


def test_links_follow_retention_and_never_create_a_file_to_purge(tmp_path):
    from app.desk.links import Links

    store = Links(tmp_path / "desk.db")
    assert store.purge(90) == 0 and store.lookup(7) is None and not store.path.exists()
    store.save(7, KEY, "whatsapp", "HND-1")
    assert store.lookup("7") == {"session_key": KEY, "channel": "whatsapp", "ref": "HND-1"}
    assert store.purge(90) == 0
    assert store.purge(-1) == 1 and store.lookup(7) is None  # older than the cut-off


# --- off means off ------------------------------------------------------------------------------


def test_unchanged_when_chatwoot_is_not_configured(meta_env, monkeypatch):
    def refuse(request):
        raise AssertionError(f"Chatwoot called while unconfigured: {request.url}")

    monkeypatch.setattr(chatwoot, "client", chatwoot.ChatwootClient(transport=httpx.MockTransport(refuse)))
    for var in ("CHATWOOT_URL", "CHATWOOT_ACCOUNT_ID", "CHATWOOT_INBOX_ID", "CHATWOOT_API_TOKEN",
                "CHATWOOT_WEBHOOK_SECRET"):
        monkeypatch.delenv(var, raising=False)
    assert config.handoff_mode("whatsapp") == "callback"
    handoff(meta_env)
    session = session_state(meta_env)
    assert session.active_flow == "lead"  # the callback flow, exactly as before H2
    assert session.bot_paused_until == 0 and bridge.CONVERSATION_SLOT not in session.slots
    assert not (meta_env.tmp / "desk.db").exists()
    assert hook(meta_env, {"event": "x"}, secret="anything").status_code == 404


def test_half_configured_counts_as_off(monkeypatch):
    _configure(monkeypatch)
    assert config.handoff_mode("whatsapp") == "inbox"
    monkeypatch.delenv("CHATWOOT_API_TOKEN")
    assert config.handoff_mode("whatsapp") == "callback"


def test_kill_switch_sends_new_handoffs_back_to_callbacks(meta_env, desk, monkeypatch):
    monkeypatch.setenv("CHATWOOT_ENABLED", "false")
    assert config.handoff_mode("whatsapp") == "callback"
    assert config.handoff_mode("messenger") == "inbox"  # Messenger keeps the Page Inbox (M4)
    handoff(meta_env)
    assert desk.requests == [] and session_state(meta_env).active_flow == "lead"


def test_a_chatwoot_outage_leaves_the_bot_answering(meta_env, desk):
    desk.fail["/conversations"] = 503
    handoff(meta_env)
    assert len([r for r in desk.requests if r["url"].endswith("/conversations")]) == chatwoot.MAX_ATTEMPTS
    session = session_state(meta_env)
    assert session.bot_paused_until == 0 and bridge.CONVERSATION_SLOT not in session.slots
    (failed,) = events("desk_failed")
    assert "HTTP 503" in failed["text"]
    wa(meta_env, "what is etumba")
    assert "mobile wallet" in meta_env.sent_texts("whatsapp")[-1]

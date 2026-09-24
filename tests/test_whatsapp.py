"""WhatsApp channel (W2-W8, P4), driven with recorded webhook payloads."""

import json
import sqlite3
import time
from pathlib import Path

import httpx
import pytest

from app import audit, config
from app.channels import whatsapp
from app.channels.base import InboundMessage

WA = Path(__file__).parent / "data" / "wa"
RAW_NUMBER = "260977123456"


def payload(name, ts=None, **overrides):
    text = (WA / f"{name}.json").read_text(encoding="utf-8").replace("TS", str(int(ts or time.time())))
    body = json.loads(text)
    msg = body["entry"][0]["changes"][0]["value"].get("messages", [{}])[0]
    for k, v in overrides.items():
        if k == "text":
            msg["text"] = {"body": v}
            msg["type"] = "text"
        else:
            msg[k] = v
    return body


def say(meta_env, text, msg_id=None, ts=None):
    body = payload("text", ts=ts, text=text, id=msg_id or f"wamid.{time.time_ns()}")
    assert meta_env.post("whatsapp", body).status_code == 200
    meta_env.process()


# --- W2: handshake, signature, durable inbox ------------------------------------------


def test_verify_handshake(meta_env):
    ok = meta_env.client.get("/webhooks/whatsapp", params={
        "hub.mode": "subscribe", "hub.verify_token": meta_env.VERIFY_TOKEN, "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    bad = meta_env.client.get("/webhooks/whatsapp", params={
        "hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"})
    assert bad.status_code == 403


def test_verify_refuses_when_no_token_configured(meta_env, monkeypatch):
    monkeypatch.delenv("WA_VERIFY_TOKEN")
    r = meta_env.client.get("/webhooks/whatsapp", params={
        "hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"})
    assert r.status_code == 403


def test_bad_or_missing_signature_is_rejected_and_nothing_stored(meta_env):
    body = payload("text")
    assert meta_env.post("whatsapp", body, signature="sha256=deadbeef").status_code == 401
    assert meta_env.post("whatsapp", body, signature="").status_code == 401
    assert meta_env.inbox.counts() == {}


def test_good_signature_stores_and_answers(meta_env):
    assert meta_env.post("whatsapp", payload("text")).status_code == 200
    meta_env.process()
    texts = meta_env.sent_texts("whatsapp")
    assert any("mobile wallet" in t for t in texts)
    assert any("automated helper" in t for t in texts)  # first contact discloses (§3.4)


def test_duplicate_delivery_is_processed_once(meta_env):
    body = payload("text", id="wamid.DUP1")
    meta_env.post("whatsapp", body)
    meta_env.post("whatsapp", body)  # Meta delivers at least once
    meta_env.process()
    meta_env.post("whatsapp", body)  # even after processing
    meta_env.process()
    assert meta_env.inbox.counts() == {"done": 1}
    assert len(meta_env.sent_texts("whatsapp")) == 1


def test_a_burst_is_answered_in_order(meta_env):
    for i, text in enumerate(["hi", "I lost my card", "pls help"]):
        meta_env.post("whatsapp", payload("text", text=text, id=f"wamid.B{i}"))
    meta_env.process()
    (session_row,) = sqlite3.connect(meta_env.tmp / "sessions.db").execute("SELECT state FROM sessions").fetchall()
    state = json.loads(session_row[0])
    said = [t["text"] for t in state["transcript"] if t["role"] == "user"]
    assert said == ["hi", "I lost my card", "pls help"]
    assert state["active_flow"] == "fraud"


def test_a_crash_leaves_the_message_for_a_retry(meta_env):
    box = meta_env.inbox
    box.store(InboundMessage("whatsapp", RAW_NUMBER, text="hello", msg_id="wamid.CRASH"))

    def boom(msg, findings):
        raise RuntimeError("worker died")

    box.process_pending(boom)
    assert box.counts() == {"new": 1}  # still there after the "restart"
    seen = []
    box.process_pending(lambda msg, f: seen.append(msg.text))
    assert seen == ["hello"] and box.counts() == {"done": 1}


def test_a_message_that_keeps_failing_is_parked(meta_env):
    box = meta_env.inbox
    box.store(InboundMessage("whatsapp", RAW_NUMBER, text="x", msg_id="wamid.BAD"))
    for _ in range(5):
        box.process_pending(lambda m, f: 1 / 0)
    assert box.counts() == {"failed": 1}


# --- W3: parsing -------------------------------------------------------------------------


def test_parse_every_message_type():
    now = time.time()
    msgs = {}
    for name in ("text", "button_reply", "list_reply", "location", "image", "audio", "bsuid"):
        (m,), _ = whatsapp.parse(payload(name, ts=now))
        msgs[name] = m
    assert msgs["text"].text == "what is etumba"
    assert msgs["button_reply"].payload == "etumba_what_is"
    assert msgs["list_reply"].payload == "loc_city:Kitwe"
    assert msgs["location"].location == (-12.809, 28.214)
    assert msgs["image"].media_type == "image" and msgs["audio"].media_type == "audio"
    assert msgs["text"].user_key == RAW_NUMBER and msgs["text"].phone_hint == RAW_NUMBER
    assert msgs["bsuid"].user_key == "ZM.BSUID.abc123"  # the BSUID wins over the wa_id
    assert abs(msgs["text"].ts - now) < 2


def test_statuses_are_logged_with_a_hashed_recipient(meta_env):
    meta_env.post("whatsapp", payload("status"))
    rows = [json.loads(l) for l in audit.JSONL_FILE.read_text(encoding="utf-8").splitlines()]
    (row,) = [r for r in rows if r["action"] == "wa_status:failed"]
    assert "131047" in row["text"] and RAW_NUMBER not in json.dumps(row)


# --- W4: sending ---------------------------------------------------------------------------


def _transport(codes, seen):
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(codes.pop(0) if codes else 200, json={})

    return httpx.MockTransport(handler)


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("WA_ACCESS_TOKEN", "token")
    monkeypatch.setenv("WA_PHONE_NUMBER_ID", "PHONE_ID")


def test_retries_5xx_and_429_then_succeeds(live, isolated_data):
    seen = []
    sender = whatsapp.WhatsAppSender(transport=_transport([500, 429, 200], seen), sleep=lambda s: None)
    assert sender.send(RAW_NUMBER, [{"text": "hi", "buttons": [{"label": "A", "payload": "a"}]}])
    assert len(seen) == 3
    body = seen[-1]
    assert body["to"] == RAW_NUMBER and body["messaging_product"] == "whatsapp"
    assert body["interactive"]["type"] == "button"


def test_a_permanent_failure_is_not_retried_and_is_audited(live, isolated_data):
    seen = []
    sender = whatsapp.WhatsAppSender(transport=_transport([400], seen), sleep=lambda s: None)
    assert not sender.send(RAW_NUMBER, [{"text": "hi", "buttons": [{"label": "A", "payload": "a"}]}])
    assert len(seen) == 1
    log = audit.JSONL_FILE.read_text(encoding="utf-8")
    assert "send_failed" in log and RAW_NUMBER not in log


def test_gives_up_after_five_attempts(live, isolated_data):
    seen = []
    sender = whatsapp.WhatsAppSender(transport=_transport([503] * 9, seen), sleep=lambda s: None)
    assert not sender.send(RAW_NUMBER, [{"text": "hi", "buttons": [{"label": "A", "payload": "a"}]}])
    assert len(seen) == 5


def test_main_menu_goes_out_as_a_list(meta_env):
    say(meta_env, "hi")
    lists = [m for m in meta_env.outbox("whatsapp") if m.get("type") == "interactive"]
    assert lists[-1]["interactive"]["type"] == "list"
    ids = {r["id"] for s in lists[-1]["interactive"]["action"]["sections"] for r in s["rows"]}
    assert "human_handoff" in ids


def test_read_receipt_and_typing_indicator(meta_env):
    say(meta_env, "what is etumba", msg_id="wamid.READ1")
    reads = [m for m in meta_env.outbox("whatsapp") if m.get("status") == "read"]
    assert reads and reads[0]["message_id"] == "wamid.READ1" and reads[0]["typing_indicator"]


# --- W5: media, W6: location ------------------------------------------------------------------


def test_images_are_refused_and_nothing_is_downloaded(meta_env):
    meta_env.post("whatsapp", payload("image"))
    meta_env.process()
    text = " ".join(meta_env.sent_texts("whatsapp"))
    assert "can't accept photos" in text
    log = audit.JSONL_FILE.read_text(encoding="utf-8")
    assert "[media: image]" in log and "MEDIA_ID" not in log


def test_voice_notes_get_their_own_reply(meta_env):
    meta_env.post("whatsapp", payload("audio"))
    meta_env.process()
    assert any("voice notes" in t for t in meta_env.sent_texts("whatsapp"))


def test_shared_location_finds_the_nearest_branch(meta_env):
    meta_env.post("whatsapp", payload("location"))  # near Chisokone Market, Kitwe
    meta_env.process()
    text = meta_env.sent_texts("whatsapp")[-1]
    assert text.index("Kitwe Branch") < text.index("Ndola Branch")
    assert "-12.809" not in audit.JSONL_FILE.read_text(encoding="utf-8")  # coordinates not logged


def test_old_city_button_from_a_list_still_works(meta_env):
    meta_env.post("whatsapp", payload("list_reply"))
    meta_env.process()
    assert "Chisokone" in meta_env.sent_texts("whatsapp")[-1]


# --- W3 prefill: the number the customer writes from -----------------------------------------


def test_fraud_contact_offers_the_whatsapp_number_ending_only(meta_env):
    say(meta_env, "i think i was scammed")
    say(meta_env, "they called pretending to be the bank")
    say(meta_env, "yesterday")
    say(meta_env, "eTumba")
    last = meta_env.outbox("whatsapp")[-1]
    assert "ending 456" in last["interactive"]["body"]["text"]
    ids = [b["reply"]["id"] for b in last["interactive"]["action"]["buttons"]]
    assert "contact:use_hint" in ids
    body = payload("button_reply")
    body["entry"][0]["changes"][0]["value"]["messages"][0]["interactive"]["button_reply"]["id"] = "contact:use_hint"
    body["entry"][0]["changes"][0]["value"]["messages"][0]["id"] = "wamid.HINT"
    meta_env.post("whatsapp", body)
    meta_env.process()
    (fields,) = sqlite3.connect(audit.DB_FILE).execute("SELECT fields FROM tickets").fetchone()
    assert json.loads(fields)["contact"] == "0977123456"


# --- W8: stale messages and the 24-h window ---------------------------------------------------


def test_stale_message_gets_an_apology_not_a_silent_resume(meta_env):
    say(meta_env, "i think i was scammed")
    old = time.time() - (config.STALE_MESSAGE_MINUTES + 5) * 60
    say(meta_env, "they called pretending to be the bank", ts=old)
    assert "slow reply" in meta_env.sent_texts("whatsapp")[-1]
    (row,) = sqlite3.connect(meta_env.tmp / "sessions.db").execute("SELECT state FROM sessions").fetchall()
    assert "what_happened" not in json.loads(row[0])["flow_state"].get("data", {})


def test_free_form_outside_the_window_is_refused_but_a_template_is_allowed(isolated_data):
    from app.session import Session

    s = Session(id="x", created=0, last_active=0, channel="whatsapp",
                last_inbound_at=time.time() - 25 * 3600)
    with pytest.raises(whatsapp.WindowClosed):
        whatsapp.sender.send_free_form(RAW_NUMBER, [{"text": "hi", "buttons": []}], s)
    assert whatsapp.sender.send_template(RAW_NUMBER, "case_update", ref="FRD-20260924-ABCD")
    s.last_inbound_at = time.time() - 3600
    assert whatsapp.window_open(s)


# --- P4: kill switch and per-user limits -------------------------------------------------------


def test_kill_switch_sends_one_static_reply_then_stays_quiet(meta_env, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ENABLED", "0")
    say(meta_env, "hello")
    say(meta_env, "hello again")
    texts = meta_env.sent_texts("whatsapp")
    assert len(texts) == 1 and "not available on this channel" in texts[0]
    assert "888" in texts[0]


def test_per_user_limit_does_not_throttle_other_customers(meta_env, monkeypatch):
    monkeypatch.setattr(config, "USER_RATE_LIMIT_PER_MINUTE", 2)
    for i in range(4):
        say(meta_env, f"what is etumba {i}")
    other = payload("text", text="what is etumba", id="wamid.OTHER", **{"from": "260966000111"})
    other["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"] = "260966000111"
    meta_env.post("whatsapp", other)
    meta_env.process()
    log = audit.JSONL_FILE.read_text(encoding="utf-8")
    assert log.count("rate_limited") == 2
    assert len([t for t in meta_env.sent_texts("whatsapp") if "mobile wallet" in t]) == 3


# --- privacy: the raw number is stored nowhere readable -----------------------------------------


def test_raw_number_is_nowhere_in_logs_sessions_or_the_processed_inbox(meta_env):
    say(meta_env, "my pin is 1234 and i lost my card")
    for path in (audit.JSONL_FILE, meta_env.tmp / "sessions.db"):
        assert RAW_NUMBER.encode() not in path.read_bytes(), path
    events = sqlite3.connect(audit.DB_FILE).execute("SELECT session_id, user_hash, text FROM events").fetchall()
    assert all(RAW_NUMBER not in " ".join(str(c) for c in row) for row in events)
    assert "1234" not in audit.JSONL_FILE.read_text(encoding="utf-8")
    inbox_rows = sqlite3.connect(meta_env.tmp / "inbox.db").execute("SELECT user_ref, message FROM inbound").fetchall()
    assert all(ref is None and RAW_NUMBER not in raw and "1234" not in raw for ref, raw in inbox_rows)

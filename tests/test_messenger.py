"""Messenger channel (M2 adapter, M4 handover, M5 comments), driven with
recorded webhook sequences."""

import json
import sqlite3
import time
from pathlib import Path

from app import audit
from app.channels import messenger

MS = Path(__file__).parent / "data" / "ms"
PSID = "PSID_1234567"


def payload(name, **message_overrides):
    raw = (MS / f"{name}.json").read_text(encoding="utf-8")
    raw = raw.replace('"TSMS"', str(int(time.time() * 1000))).replace('"TS"', str(int(time.time())))
    body = json.loads(raw)
    if message_overrides:
        body["entry"][0]["messaging"][0]["message"].update(message_overrides)
    return body


def send(meta_env, name, **overrides):
    assert meta_env.post("messenger", payload(name, **overrides)).status_code == 200
    meta_env.process()


def say(meta_env, text):
    send(meta_env, "text", text=text, mid=f"m_{time.time_ns()}")


def replies(meta_env):
    return [m for m in meta_env.outbox("messenger") if "message" in m and "text" in m["message"]]


# --- M2 ----------------------------------------------------------------------------------


def test_verify_and_signature(meta_env):
    ok = meta_env.client.get("/webhooks/messenger", params={
        "hub.mode": "subscribe", "hub.verify_token": meta_env.VERIFY_TOKEN, "hub.challenge": "c"})
    assert ok.status_code == 200 and ok.text == "c"
    assert meta_env.post("messenger", payload("text"), signature="sha256=00").status_code == 401


def test_text_gets_an_answer_with_quick_replies(meta_env):
    send(meta_env, "text")
    (reply,) = replies(meta_env)
    assert "mobile wallet" in reply["message"]["text"]
    assert "automated helper" in reply["message"]["text"]  # first contact discloses
    quick = reply["message"]["quick_replies"]
    assert 1 <= len(quick) <= 13 and all(len(q["title"]) <= 20 for q in quick)
    assert reply["messaging_type"] == "RESPONSE"


def test_get_started_postback_shows_the_menu(meta_env):
    send(meta_env, "postback")
    (reply,) = replies(meta_env)
    payloads = {q["payload"] for q in reply["message"]["quick_replies"]}
    assert "human_handoff" in payloads


def test_seen_and_typing_are_sent(meta_env):
    send(meta_env, "text")
    actions = [m["sender_action"] for m in meta_env.outbox("messenger") if "sender_action" in m]
    assert actions[:2] == ["mark_seen", "typing_on"]


def test_psid_never_reaches_the_logs(meta_env):
    send(meta_env, "text")
    say(meta_env, "i lost my card")
    assert PSID not in audit.JSONL_FILE.read_text(encoding="utf-8")
    assert PSID.encode() not in (meta_env.tmp / "sessions.db").read_bytes()
    assert PSID not in json.dumps(meta_env.outbox("messenger"))


# --- M4: handover to the Page Inbox -------------------------------------------------------


def test_talk_to_a_person_hands_the_thread_to_the_page_inbox(meta_env):
    say(meta_env, "hello")
    send(meta_env, "quick_reply")  # "Talk to a person"
    last = replies(meta_env)[-1]["message"]["text"]
    assert "a person will reply to you right here" in last and "HND-" in last
    passes = [m for m in meta_env.outbox("messenger") if m["path"] == "me/pass_thread_control"]
    assert passes and passes[0]["target_app_id"] == messenger.PAGE_INBOX_APP_ID
    (kind, fields) = sqlite3.connect(audit.DB_FILE).execute("SELECT type, fields FROM tickets").fetchone()
    assert kind == "handoff"
    before = len(replies(meta_env))
    say(meta_env, "are you there?")  # the bot stays quiet while a person helps
    assert len(replies(meta_env)) == before
    assert "paused" in audit.JSONL_FILE.read_text(encoding="utf-8")


def test_typed_request_for_a_person_hands_over_too(meta_env):
    say(meta_env, "hello")
    say(meta_env, "talk to a person")
    assert any(m["path"] == "me/pass_thread_control" for m in meta_env.outbox("messenger"))


def test_an_unfinished_fraud_report_rides_on_the_handoff_ticket(meta_env):
    say(meta_env, "i think i was scammed")
    say(meta_env, "they called pretending to be the bank")
    send(meta_env, "quick_reply")
    (fields,) = sqlite3.connect(audit.DB_FILE).execute("SELECT fields FROM tickets").fetchone()
    assert "pretending to be the bank" in json.loads(fields)["unfinished_fraud"]["what_happened"]


def test_a_person_replying_pauses_the_bot_and_done_resumes_it(meta_env):
    say(meta_env, "hello")
    send(meta_env, "echo_page_inbox")  # a person replied from the inbox
    before = len(replies(meta_env))
    say(meta_env, "thanks")
    assert len(replies(meta_env)) == before
    send(meta_env, "thread_back")  # the agent marked it Done
    say(meta_env, "what is etumba")
    assert len(replies(meta_env)) == before + 1


def test_the_bots_own_echoes_do_not_pause_it(meta_env):
    say(meta_env, "hello")
    send(meta_env, "echo_our_app")
    before = len(replies(meta_env))
    say(meta_env, "what is etumba")
    assert len(replies(meta_env)) == before + 1


def test_standby_messages_are_logged_not_answered(meta_env):
    send(meta_env, "standby")
    assert replies(meta_env) == []
    assert "thanks mary" in audit.JSONL_FILE.read_text(encoding="utf-8")


# --- M5: private replies to urgent comments ------------------------------------------------


def test_urgent_comment_gets_one_private_reply(meta_env):
    body = payload("comment_urgent")
    meta_env.post("messenger", body)
    meta_env.post("messenger", body)  # redelivered
    meta_env.process()
    sent = [m for m in meta_env.outbox("messenger") if m["path"] == "me/messages"]
    assert len(sent) == 1
    assert "call" in sent[0]["message"]["text"] and "never share your PIN" in sent[0]["message"]["text"]
    assert not [m for m in meta_env.outbox("messenger") if m["path"].endswith("/comments")]  # no public reply
    assert "comment_private:fraud" in audit.JSONL_FILE.read_text(encoding="utf-8")
    assert "FB_USER_777" not in audit.JSONL_FILE.read_text(encoding="utf-8")


def test_ordinary_comments_are_left_to_people(meta_env):
    meta_env.post("messenger", payload("comment_plain"))
    meta_env.process()
    assert meta_env.outbox("messenger") == []
    assert "comment_ignored" in audit.JSONL_FILE.read_text(encoding="utf-8")


def test_public_reply_only_when_the_po_enables_it(meta_env, monkeypatch):
    monkeypatch.setenv("MESSENGER_PUBLIC_REPLIES", "1")
    meta_env.post("messenger", payload("comment_urgent"))
    meta_env.process()
    public = [m for m in meta_env.outbox("messenger") if m["path"].endswith("/comments")]
    assert len(public) == 1 and public[0]["message"] == "We've sent you a private message so we can help."



# --- M3: the Page profile, as code -----------------------------------------------------------


def test_page_profile_payload():
    from admin.messenger_profile import GREETING_MAX, MENU_TITLE_MAX, build_profile

    profile = build_profile()
    assert profile["get_started"] == {"payload": "start"}
    greeting = profile["greeting"][0]["text"]
    assert len(greeting) <= GREETING_MAX and "automated" in greeting and "not a person" in greeting
    menu = profile["persistent_menu"][0]["call_to_actions"]
    assert any(item["payload"] == "human_handoff" for item in menu)  # always a way to a person
    assert all(len(item["title"]) <= MENU_TITLE_MAX for item in menu)
    breakers = profile["ice_breakers"][0]["call_to_actions"]
    assert 3 <= len(breakers) <= 4 and all(b["question"] for b in breakers)

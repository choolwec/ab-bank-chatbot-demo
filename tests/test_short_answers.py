"""Short answers first, "More details" for the full text; small talk on the
whole message only; "clear chat" starts a fresh conversation."""
import re

import pytest

from app.router import DETAILS_PREFIX, _render, matcher as M
SHORT = {name: i for name, i in M.intents.items() if i.get("answer_short")}
SMALL_TALK = {name: i for name, i in M.intents.items() if i.get("match") == "exact"}


def _words(text):
    return len(re.sub(r"{\w+}", "X", text).split())  # a contact placeholder is one word


def test_long_answers_have_a_short_version():
    assert len(SHORT) >= 35
    for name, intent in M.intents.items():
        if intent.get("wording") == "flow_doc":
            continue  # the team's flow document: its wording, at its length
        if intent.get("answer") and not intent.get("flow") and _words(intent["answer"]) > 40:
            assert name in SHORT, f"{name}: {_words(intent['answer'])} words and no answer_short"


@pytest.mark.parametrize("name", sorted(SHORT))
def test_short_answer_is_short_and_clean(name):
    intent = SHORT[name]
    short, full = intent["answer_short"], intent["answer"]
    assert "[CONFIRM" not in short and "[VERIFY" not in short, name
    assert short.strip() != full.strip(), name
    if intent.get("wording") == "flow_doc":
        return  # the team's flow document: its wording, at its length
    assert _words(short) <= 32, name
    assert _words(short) < _words(full), name
    assert set(re.findall(r"{(\w+)}", short)) <= set(re.findall(r"{(\w+)}", full)) | {"contact_phone"}, name


def test_short_answer_first_then_details(bot):
    b = bot()
    b.tap("savings_account")
    assert b.text == _render(SHORT["savings_account"]["answer_short"])
    # The lead button first, then "More details".
    assert b.buttons[:2] == ["lead:savings_account", DETAILS_PREFIX + "savings_account"]

    b.tap(DETAILS_PREFIX + "savings_account")
    assert b.action == "details"
    assert "Minimum balance: ZMW 100" in b.text
    assert DETAILS_PREFIX + "savings_account" not in b.buttons


def test_typed_question_gets_the_short_answer(bot):
    b = bot()
    b.say("how do i open a savings acount")
    assert b.action == "answer"
    assert b.text == _render(SHORT[b.last[1]["intent"]]["answer_short"])
    assert any(p.startswith(DETAILS_PREFIX) for p in b.buttons[:2])


def test_channel_variant_still_wins_on_whatsapp(bot):
    wa = bot(channel="whatsapp")
    wa.tap("contact_details")
    assert "already chatting" in wa.text
    assert not any(p.startswith(DETAILS_PREFIX) for p in wa.buttons)


@pytest.mark.parametrize("text, intent", [
    ("how are you", "how_are_you"),
    ("How r u?", "how_are_you"),
    ("I'm fine, and you?", "small_talk_fine"),
    ("what's your name", "bot_name"),
    ("ok", "acknowledgement"),
    ("thank you", "thanks_goodbye"),
    ("nice to meet you", "nice_to_meet_you"),
    ("are you there?", "are_you_there"),
    ("haha", "compliment"),
])
def test_small_talk(bot, text, intent):
    b = bot()
    b.say(text)
    assert b.last[1].get("intent") == intent, b.last
    assert len(b.text.split()) <= 20
    assert b.buttons  # never a dead end


def test_small_talk_only_on_the_whole_message():
    assert M.match("how are you")[0][0] == "how_are_you"
    top = M.match("how are your loans priced")[0][0]
    assert top not in SMALL_TALK
    for intent in SMALL_TALK.values():
        assert intent["phrases"], intent["intent"]  # an exact intent needs its phrases


def test_greeting_is_the_documents_welcome_and_discloses(bot):
    from app.messages import msg

    b = bot()
    b.say("hello")
    assert b.last[1].get("intent") == "greeting"
    assert "automated assistant" in b.text and "not a person" not in b.text
    assert b.text == msg("welcome")


# --- Clear chat -----------------------------------------------------------------

@pytest.mark.parametrize("typed", ["clear chat", "start over", "Restart", "new chat"])
def test_typed_clear_starts_fresh(bot, typed):
    b = bot()
    b.say("what is etumba")
    b.say(typed)
    assert b.action == "restart"
    assert "automated assistant" in b.text
    assert b.session.active_flow is None
    assert "context" not in b.session.slots
    # Only this turn is left: the customer's command and the welcome.
    assert [t["role"] for t in b.session.transcript] == ["bot"]


def test_clear_drops_a_callback_without_asking(bot):
    b = bot()
    b.say("Can someone call me back about a loan?")
    assert b.session.active_flow == "lead"
    b.tap("restart")
    assert b.action == "restart" and b.session.active_flow is None


def test_clear_asks_first_during_a_fraud_report(bot):
    b = bot()
    b.say("someone stole my card")
    assert b.session.active_flow == "fraud"
    b.tap("restart")
    assert b.action == "restart_confirm"
    assert b.session.active_flow == "fraud"
    b.say("no")
    assert b.action == "cancel_declined" and b.session.active_flow == "fraud"
    b.say("clear chat")
    b.say("yes")
    assert b.action == "restart" and b.session.active_flow is None


def test_clear_keeps_a_marketing_opt_out(bot):
    b = bot()
    b.say("unsubscribe")
    b.say("clear chat")
    assert b.session.slots.get("marketing_opt_out")


def test_widget_restart_over_http(client):
    first = client.post("/chat", json={"message": "what is etumba"}).json()
    sid = first["session_id"]
    data = client.post("/chat", json={"session_id": sid, "payload": "restart"}).json()
    assert data["session_id"] == sid
    assert data["meta"]["action"] == "restart"
    assert data["replies"][-1]["buttons"]
    assert not any(k in data["replies"][-1] for k in ("yes", "no", "resolved"))

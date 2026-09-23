"""C5: frustration without swearing gets calm + a person, never a strike."""

import pytest

from app import guards

FRUSTRATED = [
    "this is not helping",
    "you are not understanding me",
    "you don't understand",
    "I already told you that",
    "what a waste of time",
    "useless bot",
    "i'm going in circles here",
    "I am so frustrated",
    "hello??!!!",
    "I NEED TO SPEAK TO SOMEBODY NOW",
]
NOT_FRUSTRATED = [
    "is it helpful to open a savings account?",
    "how can you help me",
    "what is etumba",
    "i understand, thanks",
    "please tell me the opening hours",
    "ETUMBA",
    "hi!",
]


@pytest.mark.parametrize("text", FRUSTRATED)
def test_frustrated(bot, text):
    b = bot()
    b.say("flurb zzqx")  # one strike already
    b.say(text)
    assert b.action == "frustration", (text, b.action)
    assert b.session.strikes == 1  # unchanged: never a strike
    assert "human_handoff" in b.buttons


@pytest.mark.parametrize("text", NOT_FRUSTRATED)
def test_not_frustrated(bot, text):
    b = bot()
    b.say(text)
    assert b.action != "frustration", (text, b.action)


def test_capitals_that_can_be_answered_are_answered(bot):
    """Many customers type in capitals from habit (feature phones)."""
    assert guards.frustration_kind("WHAT IS ETUMBA") == "caps"
    b = bot()
    b.say("WHAT IS ETUMBA")
    assert b.action == "answer" and b.last[1]["intent"] == "etumba_what_is"


def test_frustration_mid_callback_keeps_the_step(bot):
    b = bot()
    b.tap("human_handoff")
    b.say("Mary")
    b.say("you are not listening to me")
    assert b.action == "frustration"
    assert b.session.active_flow == "lead"
    assert "phone number" in b.text.lower()
    b.say("0977123456")
    assert b.session.flow_state["data"]["phone"] == "0977123456"


def test_frustration_inside_a_complaint_is_the_complaint(bot):
    b = bot()
    b.say("I want to complain")
    b.say("Service at a branch")
    b.say("your staff are not helping and it is a waste of time")
    assert b.session.flow_state["data"]["details"].startswith("your staff")

"""S1: urgent detection recall and precision, measured on data files.

Positive lines must reach their flow, directly or after a "yes" to the
confirmation question. Negative lines must never open a flow. Ask-first lines
are questions *about* fraud: they must confirm, never hijack.
"""

from pathlib import Path

import pytest

from app import guards
from app.router import URGENT_NO, URGENT_YES

DATA = Path(__file__).parent / "data"


def _lines(name):
    out = []
    for line in (DATA / name).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


POSITIVE = [tuple(p.strip() for p in l.split("|", 1)) for l in _lines("urgent_positive.txt")]
NEGATIVE = _lines("urgent_negative.txt")
ASK_FIRST = _lines("urgent_ask_first.txt")


def test_corpus_sizes():
    assert len(POSITIVE) >= 60
    assert len(NEGATIVE) >= 30


@pytest.mark.parametrize("kind,text", POSITIVE)
def test_positive_reaches_its_flow(bot, kind, text):
    b = bot()
    b.say(text)
    if b.action == f"urgent_confirm:{kind}":
        assert URGENT_YES in b.buttons
        b.tap(URGENT_YES)
    assert b.action == f"urgent:{kind}", (text, b.action, b.text)
    assert b.session.active_flow == kind


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative_is_not_urgent(bot, text):
    assert guards.urgent_scan(text) is None, (text, guards.urgent_scan(text))
    b = bot()
    b.say(text)
    # Acceptance: no negative line opens a flow without confirmation. The
    # fuzzy matcher may still *ask* (see router._free_text).
    assert not b.action.startswith("urgent:"), (text, b.action)
    assert b.session.active_flow not in ("fraud", "complaint"), text


@pytest.mark.parametrize("text", ASK_FIRST)
def test_questions_about_fraud_ask_first(text):
    signal = guards.urgent_scan(text)
    assert signal is not None and not signal.is_hard, (text, signal)


# --- S1 change 3: the intro depends on what was taken ---


def test_money_theft_gets_money_intro_not_card_block(bot):
    b = bot()
    b.say("someone stole money from my etumba")
    assert b.session.flow_state["kind"] == "fraud"
    assert "secure your card" not in b.text.lower()


def test_card_theft_gets_card_block_intro(bot):
    b = bot()
    b.say("my card was stolen")
    assert b.session.flow_state["kind"] == "lost_card"
    assert "block your card" in b.text.lower()


# --- Soft-signal confirmation paths ---


def test_soft_signal_typed_yes_starts_fraud(bot):
    b = bot()
    b.say("my money is gone")
    assert b.action == "urgent_confirm:fraud"
    assert b.session.active_flow is None
    b.say("yes")
    assert b.action == "urgent:fraud"


def test_soft_signal_no_answers_the_question_instead(bot):
    b = bot()
    b.say("my balance is wrong, how do i check my etumba balance")
    assert b.action == "urgent_confirm:fraud"
    b.tap(URGENT_NO)
    assert b.action == "urgent_declined"
    assert b.session.active_flow is None
    assert b.last[1].get("declined_answer") == "answer", b.last[1]
    assert "balance" in b.text.lower()


def test_soft_signal_no_never_costs_a_strike(bot):
    b = bot()
    b.say("my money is gone")
    b.say("no")
    assert b.action == "urgent_declined"
    assert b.session.strikes == 0


def test_soft_signal_mid_flow_no_resumes_the_flow(bot):
    b = bot()
    b.tap("human_handoff")
    b.say("Mary")
    b.say("0977123456")
    b.say("my money is gone")  # at the topic step
    assert b.action == "urgent_confirm:fraud"
    b.tap(URGENT_NO)
    assert b.session.active_flow == "lead"
    assert "what would you like to discuss" in b.text.lower()


def test_pending_confirmation_expires_after_one_message(bot):
    b = bot()
    b.say("my money is gone")
    b.say("what is etumba")
    b.say("yes")  # no longer answers the stale question
    assert b.action != "urgent:fraud"


def test_stale_confirmation_button_is_harmless(bot):
    b = bot()
    b.tap(URGENT_YES)
    assert b.session.active_flow is None
    assert b.buttons


def test_negation_never_suppresses_a_hard_signal():
    signal = guards.urgent_scan("I didn't get an SMS and now my money is stolen")
    assert signal and signal.is_hard
    signal = guards.urgent_scan("i dont know who but someone took my money")
    assert signal and signal.is_hard


def test_matcher_only_urgent_match_asks_first(bot):
    b = bot()
    b.say("i am happy with the service, thank you")
    assert b.session.active_flow is None
    assert b.action in ("urgent_confirm:complaint", "answer", "did_you_mean", "fallback")


def test_report_fraud_button_still_starts_flow_directly(bot):
    b = bot()
    b.tap("fraud_scam")
    assert b.session.active_flow == "fraud"


def test_menu_tap_drops_pending_confirmation(bot):
    b = bot()
    b.say("my money is gone")
    b.tap("menu")
    b.say("yes")
    assert b.action != "urgent:fraud"


def test_stale_confirmation_button_mid_flow_keeps_the_flow(bot):
    b = bot()
    b.tap("human_handoff")
    b.say("Mary")
    b.tap(URGENT_YES)
    assert b.session.active_flow == "lead"
    assert b.session.flow_state["data"] == {"name": "Mary"}

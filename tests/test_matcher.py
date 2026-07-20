"""Regression suite over the intent knowledge base (acceptance §3.5).

Every phrase in every intent must reach its own intent. Content edits are
deploys — this suite gates them (§6).
"""

import pytest

from app import config
from app.router import matcher


def test_launch_intent_count():
    assert len(matcher.intents) >= 25


def test_every_intent_has_label_and_answer_or_flow():
    for name, intent in matcher.intents.items():
        assert intent.get("label"), name
        assert intent.get("answer") or intent.get("flow"), name


def test_every_answer_has_buttons():
    # No dead ends is also enforced at runtime; this catches it at edit time.
    for name, intent in matcher.intents.items():
        if intent.get("answer"):
            assert intent.get("buttons"), f"{name} has an answer but no buttons"


def test_canonical_phrase_is_top1():
    for name, intent in matcher.intents.items():
        canonical = intent["phrases"][0]
        ranked = matcher.match(canonical)
        assert ranked and ranked[0][0] == name, (
            f"{name}: canonical '{canonical}' -> {ranked[:3]}"
        )


def test_all_phrases_reach_their_intent():
    failures = []
    for name, intent in matcher.intents.items():
        for phrase in intent["phrases"]:
            ranked = matcher.match(phrase)[:3]
            ok = any(n == name and s >= config.MEDIUM_CONFIDENCE for n, s in ranked)
            if not ok:
                failures.append((name, phrase, ranked))
    assert not failures, failures


@pytest.mark.parametrize(
    "query,expected",
    [
        ("wat is etumba", "etumba_what_is"),
        ("compliant", "complaint"),
        ("i want loan", "loan_apply_how"),
        ("requirements for opening acount", "account_opening_requirements"),
        ("stollen card", "lost_stolen_card"),
        ("savngs account", "savings_account"),
        ("hie", "greeting"),
        ("the app is not working", "technical_issue"),
        ("myabz is down", "technical_issue"),
        ("etumba is down", "technical_issue"),
        ("mymbs is down", "technical_issue"),
    ],
)
def test_misspellings_and_zambian_english(query, expected):
    ranked = matcher.match(query)[:3]
    assert any(n == expected for n, _ in ranked), (query, ranked)


def test_gibberish_scores_low():
    ranked = matcher.match("flurb zzqx vortblatt")
    assert not ranked or ranked[0][1] < config.MEDIUM_CONFIDENCE

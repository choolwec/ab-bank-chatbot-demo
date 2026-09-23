"""C8: facts pulled from the message that starts a fraud report. Every date
test uses a fixed "now" so results never depend on the day the suite runs."""

import datetime as dt

import pytest

from app.extract import extract

NOW = dt.datetime(2026, 9, 23, 12, 0)  # a Wednesday


@pytest.mark.parametrize(
    "text,when,hint",
    [
        ("I lost my card yesterday at cairo branch", "yesterday", "2026-09-22"),
        ("it happened this morning", "this morning", "2026-09-23"),
        ("they called me last night", "last night", "2026-09-22"),
        ("3 days ago my card was cloned", "3 days ago", "2026-09-20"),
        ("last friday someone called", "last friday", "2026-09-18"),
        ("they took money on monday", "on monday", "2026-09-21"),
        ("it happened on 12 september on internet banking", "on 12 september", "2026-09-12"),
        ("money went on 05/09/2026", "on 05/09/2026", "2026-09-05"),
    ],
)
def test_when_keeps_the_raw_words_and_a_date_hint(text, when, hint):
    facts = extract(text, NOW)
    assert facts["when"].lower() == when
    assert facts["when_hint"] == hint


@pytest.mark.parametrize(
    "text",
    [
        "they took K500 at 10am",          # a time is never a date (measured misread)
        "i may have been scammed",         # "may" is not the month
        "someone called me at 14:30",
        "it was in march",                 # a bare month is too vague to date
    ],
)
def test_no_date_invented(text):
    assert "when_hint" not in extract(text, NOW)
    assert "when" not in extract(text, NOW)


def test_vague_when_keeps_words_without_a_date():
    facts = extract("it happened last week", NOW)
    assert facts["when"] == "last week" and "when_hint" not in facts


@pytest.mark.parametrize(
    "text,channel",
    [
        ("someone stole money from my etumba", "eTumba"),
        ("they took it from my wallet", "eTumba"),
        ("my card was cloned at the atm", "Card or ATM"),
        ("someone logged into my myabz", "Internet banking"),
        ("the teller took my money", "Branch"),
        ("it happened at the kitwe branch", "Branch"),
    ],
)
def test_channel(text, channel):
    assert extract(text, NOW)["channel"] == channel


def test_branch_and_amount_hints():
    facts = extract("they took ZMW 1,200 at the chilenje branch", NOW)
    assert facts["branch_hint"] == "Chilenje Branch"
    assert facts["amount_hint"] == "K1,200"


def test_card_outranks_branch_as_the_channel():
    facts = extract("I lost my card yesterday at cairo branch", NOW)
    assert facts["channel"] == "Card or ATM" and facts["branch_hint"] == "Cairo Branch"

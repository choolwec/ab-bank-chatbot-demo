"""H3: contact-centre hours and honest out-of-hours promises."""

import datetime as dt

import pytest

from app import hours


def at(y, m, d, hh, mm=0):
    return dt.datetime(y, m, d, hh, mm, tzinfo=hours.LUSAKA)


@pytest.mark.parametrize(
    "moment,open_",
    [
        (at(2026, 9, 23, 10), True),     # Wednesday morning
        (at(2026, 9, 23, 17, 30), False),  # after 17:00
        (at(2026, 9, 26, 10), True),     # Saturday morning
        (at(2026, 9, 26, 13), False),    # Saturday afternoon
        (at(2026, 9, 27, 10), False),    # Sunday
        (at(2026, 10, 24, 10), False),   # Independence Day (a Saturday in 2026)
    ],
)
def test_is_open(moment, open_):
    assert hours.is_open(moment) is open_


def test_when_phrase():
    assert hours.when_phrase(at(2026, 9, 23, 10)) == "today"
    assert hours.when_phrase(at(2026, 9, 23, 6)) == "today"      # before opening
    assert hours.when_phrase(at(2026, 9, 23, 20)) == "tomorrow"
    assert hours.when_phrase(at(2026, 9, 26, 15)) == "on Monday"  # Saturday afternoon
    assert hours.when_phrase(at(2026, 10, 23, 20)) == "on Monday"  # Friday night, holiday Saturday


def test_timezone_is_lusaka_whatever_the_server_clock():
    utc = dt.datetime(2026, 9, 23, 15, 30, tzinfo=dt.timezone.utc)  # 17:30 in Lusaka
    assert not hours.is_open(utc)


def _out_of_hours(monkeypatch, moment):
    monkeypatch.setattr(hours, "now", lambda: moment)


def test_callback_out_of_hours_promises_the_next_working_day(bot, monkeypatch):
    _out_of_hours(monkeypatch, at(2026, 9, 26, 15))  # Saturday afternoon
    b = bot()
    b.tap("human_handoff")
    b.say("Mary")
    b.say("0977123456")
    b.say("a loan")
    b.tap("time:Morning")
    b.tap("confirm_yes")
    assert "call you on Monday" in b.text and "within one working day" not in b.text


def test_complaint_out_of_hours_says_when(bot, monkeypatch):
    _out_of_hours(monkeypatch, at(2026, 9, 23, 20))
    b = bot()
    b.say("I want to complain")
    b.say("Service at a branch")
    b.say("nobody helped me")
    b.say("skip")
    b.tap("confirm_yes")
    assert "pick this up tomorrow" in b.text


def test_fraud_always_shows_the_emergency_route(bot, monkeypatch):
    _out_of_hours(monkeypatch, at(2026, 9, 27, 2))  # Sunday 02:00
    b = bot()
    b.say("someone stole money from my etumba")
    assert "call us immediately on" in b.text

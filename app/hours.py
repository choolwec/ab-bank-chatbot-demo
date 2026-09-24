"""Contact-centre opening hours and working days (ticket H3).

Lusaka time is UTC+2 all year (no daylight saving). Hours and holidays come
from config (CONTACT_CENTRE_HOURS, PUBLIC_HOLIDAYS), so Operations can change
them without a code change. Used to make honest promises out of hours: a
callback or complaint picked up "on Monday", not "within one working day"
at 22:00 on a Friday. Fraud always shows the emergency route, whatever the
time (O1).
"""

import datetime as dt

from . import config

LUSAKA = dt.timezone(dt.timedelta(hours=2), "CAT")
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def now() -> dt.datetime:
    return dt.datetime.now(LUSAKA)


def _hours_for(day: dt.date):
    if day.isoformat() in config.public_holidays():
        return None
    return config.CONTACT_CENTRE_HOURS.get(day.weekday())


def is_open(at: dt.datetime | None = None) -> bool:
    at = (at or now()).astimezone(LUSAKA)
    hours = _hours_for(at.date())
    if not hours:
        return False
    start, end = (dt.time.fromisoformat(h) for h in hours)
    return start <= at.time() < end


def next_opening(at: dt.datetime | None = None) -> dt.datetime:
    """When a person is next at work: now if open, else the next opening."""
    at = (at or now()).astimezone(LUSAKA)
    if is_open(at):
        return at
    day = at.date()
    for offset in range(0, 15):
        d = day + dt.timedelta(days=offset)
        hours = _hours_for(d)
        if not hours:
            continue
        start = dt.datetime.combine(d, dt.time.fromisoformat(hours[0]), LUSAKA)
        if start > at:
            return start
    return at  # misconfigured: don't promise anything odd


def when_phrase(at: dt.datetime | None = None) -> str:
    """ "today", "tomorrow", or the weekday name, for the next opening."""
    at = (at or now()).astimezone(LUSAKA)
    nxt = next_opening(at)
    delta = (nxt.date() - at.date()).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    return f"on {DAY_NAMES[nxt.weekday()]}"

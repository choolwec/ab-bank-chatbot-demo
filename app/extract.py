"""Pre-fill facts from the message that started a fraud report (ticket C8).

"I lost my card yesterday at cairo branch" already says what happened, when
and where. extract() pulls out:

  when / when_hint   the customer's own words ("yesterday") -- always kept,
                     never overwritten -- plus an ISO date hint when one is
                     unambiguous. Keywords first, then dateparser, but only
                     for hits that contain a digit and aren't just a time:
                     dateparser reads "I MAY have been scammed" as 23 May and
                     is happy to turn "10am" into a date.
  channel            the service involved, in the fraud flow's own terms
  branch_hint        a branch named in the message
  amount_hint        "K500" / "ZMW 1,200"

These are hints for a person and a yes/no confirmation for the customer --
never a substitute for asking when nothing was found.
"""

import datetime as dt
import json
import re

from . import config

_WEEKDAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"
WHEN_RE = re.compile(
    r"(?i)\b(?:"
    r"just\s+now|a\s+(?:few|couple\s+of)\s+(?:minutes|hours)\s+ago|"
    r"(?:earlier\s+)?today|this\s+(?:morning|afternoon|evening|week)|tonight|"
    r"last\s+(?:night|week|month)|"
    r"(?:the\s+)?day\s+before\s+yesterday|yesterday(?:\s+(?:morning|afternoon|evening|night))?|"
    rf"(?:on\s+|last\s+|this\s+|past\s+)?(?:{_WEEKDAYS})(?:\s+(?:morning|afternoon|evening|night))?|"
    r"(?:\d+|a|one|two|three|four|five|six|seven)\s+(?:days?|weeks?|hours?)\s+ago"
    r")\b"
)
_TIME_ONLY_RE = re.compile(r"(?i)^(?:at\s+|around\s+|about\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm|h|hrs)?$")
_NUM_WORDS = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}

CHANNELS = [
    # (canonical value stored, as the channel step would record it; pattern)
    ("Card or ATM", re.compile(r"(?i)\b(?:card|cards|atm|visa|mastercard|debit\s+card)\b")),
    ("eTumba", re.compile(r"(?i)\b(?:e-?tumba|wallet|\*888#?)\b")),
    ("Internet banking", re.compile(r"(?i)\b(?:internet\s+banking|online\s+banking|myabz|my\s+abz|net\s*banking|mobile\s+app|banking\s+app)\b")),
    ("Branch", re.compile(r"(?i)\b(?:branch|teller|banking\s+hall)\b")),
]
AMOUNT_RE = re.compile(r"(?i)\b(?:k|zmw|kr)\s?(\d[\d,]*(?:\.\d{1,2})?)\b")

# Words in the canonical channel value, for the confirmation question.
CHANNEL_PHRASE = {
    "Card or ATM": "your card",
    "eTumba": "eTumba",
    "Internet banking": "internet banking",
    "Branch": "a branch",
}


def _branch_names() -> list[tuple[str, str]]:
    data = json.loads(config.BRANCHES_FILE.read_text(encoding="utf-8"))
    out = []
    for b in data["branches"]:
        short = re.sub(r"(?i)\s+(?:premium\s+)?(?:satellite\s+|promotional\s+)?(?:branch|office).*$", "", b["name"]).strip()
        out.append((short.lower(), b["name"]))
    return out


def _date_hint(raw: str, base: dt.datetime) -> str | None:
    t = raw.lower()
    if "today" in t or "this morning" in t or "this afternoon" in t or "tonight" in t or "just now" in t or "minutes ago" in t or "hours ago" in t:
        return base.date().isoformat()
    if "day before yesterday" in t:
        return (base.date() - dt.timedelta(days=2)).isoformat()
    if "yesterday" in t or "last night" in t:
        return (base.date() - dt.timedelta(days=1)).isoformat()
    m = re.search(r"(\d+|a|one|two|three|four|five|six|seven)\s+(days?|weeks?)\s+ago", t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _NUM_WORDS[m.group(1)]
        days = n * (7 if m.group(2).startswith("week") else 1)
        return (base.date() - dt.timedelta(days=days)).isoformat()
    m = re.search(_WEEKDAYS, t)
    if m:
        names = _WEEKDAYS.split("|")
        back = (base.weekday() - names.index(m.group(0))) % 7
        if back == 0 and ("last" in t or "past" in t):
            back = 7
        return (base.date() - dt.timedelta(days=back)).isoformat()
    return None  # "last week", "this week": too vague for a date


def _dateparser_when(text: str, base: dt.datetime):
    try:
        from dateparser.search import search_dates
    except ImportError:  # optional at runtime; keywords still work
        return None
    settings = {
        "PREFER_DATES_FROM": "past", "DATE_ORDER": "DMY",
        "RELATIVE_BASE": base, "RETURN_AS_TIMEZONE_AWARE": False,
    }
    for raw, when in search_dates(text, languages=["en"], settings=settings) or []:
        raw = re.sub(r"(?i)\s+(?:on|at|in|and|from|to)$", "", raw.strip())
        if not re.search(r"\d", raw) or _TIME_ONLY_RE.match(raw):
            continue  # "may", "march", "10am": not a date we can trust
        if when.date() > base.date():
            continue
        return raw, when.date().isoformat()
    return None


def extract(text: str, now: dt.datetime | None = None) -> dict:
    """Facts found in `text`. Missing facts are simply absent."""
    base = now or dt.datetime.now()
    found = {}
    m = WHEN_RE.search(text or "")
    if m:
        found["when"] = m.group(0)
        hint = _date_hint(m.group(0), base)
        if hint:
            found["when_hint"] = hint
    else:
        hit = _dateparser_when(text or "", base)
        if hit:
            found["when"], found["when_hint"] = hit
    for value, pattern in CHANNELS:
        if pattern.search(text or ""):
            found["channel"] = value
            break
    lowered = (text or "").lower()
    for short, full in _branch_names():
        if short and re.search(rf"\b{re.escape(short)}\b", lowered):
            found["branch_hint"] = full
            found.setdefault("channel", "Branch")
            break
    m = AMOUNT_RE.search(text or "")
    if m:
        found["amount_hint"] = "K" + m.group(1)
    return found

"""Campaign source attribution (MK3).

Where a conversation came from, so Marketing can see which campaign brought
which callbacks -- never who the customer is.

  web       the widget sends `source` with /chat: its script tag's
            data-campaign, else utm_campaign / utm_source from the page URL
  WhatsApp  a token in the prefilled wa.me message, "ref:cairo01" (a QR code
            or the widget's "Continue on WhatsApp" link). It is stripped
            BEFORE the router sees the text, so it never affects matching.

A source is sanitised the same way in widget.js and here (the server never
trusts the client): letters, digits, "_" and "-" only, at most 40 characters,
lower-cased. A code with 7 or more digits in a row (it could be a phone,
account or card number) or anything guards.mask() would mask is rejected
outright, so a code can never carry PII.
The first source of a session wins (first-touch attribution); it is logged
once as action=session_source, and a callback ticket carries it.
"""

import re

from . import audit, guards

SOURCE_MAX = 40
UNKNOWN = "unknown"
_DISALLOWED_RE = re.compile(r"[^A-Za-z0-9_-]")
_LONG_NUMBER_RE = re.compile(r"\d{7,}")
# "ref:CAIRO01" anywhere in the message, as a whole token.
TOKEN_RE = re.compile(r"(?i)(?<![\w:])ref:([A-Za-z0-9_-]{1,%d})(?![A-Za-z0-9_-])" % SOURCE_MAX)


def sanitise(raw) -> str | None:
    """The allowlisted, lower-cased code, or None if nothing usable is left."""
    if not raw or not isinstance(raw, str):
        return None
    code = _DISALLOWED_RE.sub("", raw)[:SOURCE_MAX].lower()
    if not code:
        return None
    if _LONG_NUMBER_RE.search(code) or guards.mask(code)[1]:
        return None  # could be a phone/account/card number: never store it
    return code


def extract(text: str) -> tuple[str | None, str]:
    """(source, text without the token). The first token counts; every token
    is removed so none reaches the matcher, the transcript or the audit log."""
    if not text:
        return None, text
    found = TOKEN_RE.findall(text)
    if not found:
        return None, text
    rest = " ".join(TOKEN_RE.sub(" ", text).split())
    return sanitise(found[0]), rest


def record(session, raw) -> str | None:
    """Store a session's source once (first touch) and log it. Returns the
    stored source, if this call set it."""
    source = sanitise(raw)
    if not source or session.slots.get("source"):
        return None
    session.slots["source"] = source
    audit.log_event(session.id, "system", f"source: {source}", action="session_source",
                    channel=session.channel, user_hash=session.user_hash)
    return source


def source_of(session) -> str:
    return session.slots.get("source") or UNKNOWN

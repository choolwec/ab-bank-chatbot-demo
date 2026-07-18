"""Input guards (§3.3): PII detect/mask, urgent-keyword scan, input hygiene.

Everything here runs BEFORE matching, flows, or logging — nothing downstream
(including the audit trail) ever sees unmasked PII.
"""

import re

from . import config

# 13-19 digit runs (spaces/dashes allowed) are card-shaped. Zambian phone
# numbers are at most 12 digits including +260, so they pass through -- the
# callback flow needs them.
CARD_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
NRC_RE = re.compile(r"\b\d{6}/\d{2}/\d\b")
# "account number is 62001234567" -- only digit runs in an account context
ACCOUNT_RE = re.compile(
    r"(?i)\b(account\s*(?:number|no\.?|#)?\s*(?:is|[:=])?\s*)(\d[\d \-]{5,})"
)
# "my pin is 1234" / "password: hunter2" -- mask the secret, keep the sentence
CRED_ASSIGN_RE = re.compile(r"(?i)\b(pin|password|passcode|otp)\b\s*(?:is|was|[:=])\s*(\S+)")
CRED_DIGITS_RE = re.compile(r"(?i)\b(pin|password|passcode|otp)\b[\s:=-]*(\d{3,})")

# Control chars, zero-width chars (U+200B..U+200F), line/paragraph separators,
# BOM -- built from codepoints so this source file stays plain ASCII.
_STRIP_CODEPOINTS = (
    list(range(0x00, 0x09)) + [0x0B, 0x0C] + list(range(0x0E, 0x20)) + [0x7F]
    + list(range(0x200B, 0x2010)) + [0x2028, 0x2029, 0xFEFF]
)
CONTROL_RE = re.compile("[" + re.escape("".join(chr(c) for c in _STRIP_CODEPOINTS)) + "]")

PII_WARNING = (
    "Please don't share card numbers, PINs or passwords in chat — I never "
    "need them, and no genuine member of staff will ever ask for them."
)

# --- Urgent-topic scan (§3.1C): runs on EVERY message, any flow state ---
LOST_CARD_PHRASES = [
    "lost my card", "lost card", "card was stolen", "card stolen", "stolen card",
    "stollen card", "card missing", "cant find my card", "can't find my card",
    "block my card", "card is gone", "stole my card", "cancel my card",
]
FRAUD_RE = re.compile(
    r"(?i)\b(?:scam\w*|fraud\w*|stolen|stollen|theft|thie(?:f|ves)|hack\w*|"
    r"unauthori[sz]ed|conned|cheated|phish\w*)\b"
)
FRAUD_PHRASES = [
    "money missing", "missing money", "money gone", "money is gone",
    "took my money", "money disappeared", "did not make", "didn't make",
    "didnt make",
]
COMPLAINT_RE = re.compile(
    r"(?i)\b(?:complain\w*|compliant|disput\w*|unacceptable|rude)\b"
)
COMPLAINT_PHRASES = ["poor service", "bad service", "terrible service", "not happy with"]

ABUSE_RE = re.compile(
    # deliberately small starter list -- extend from real transcripts (§6 loop)
    r"(?i)\b(?:fuck\w*|shit\w*|bullshit|idiot\w*|stupid|useless|rubbish)\b"
)


def clean(text: str) -> str:
    """Strip control/zero-width chars, collapse whitespace, cap length."""
    text = CONTROL_RE.sub(" ", text or "")
    text = " ".join(text.split())
    return text[: config.MAX_MESSAGE_CHARS]


def mask(text: str) -> tuple[str, list[str]]:
    """Return (masked_text, findings). Findings drive the PII warning reply."""
    findings: list[str] = []

    def _mark(kind: str) -> None:
        if kind not in findings:
            findings.append(kind)

    def _card(m: re.Match) -> str:
        _mark("card_number")
        return "[CARD REDACTED]"

    def _nrc(m: re.Match) -> str:
        _mark("nrc")
        return "[NRC REDACTED]"

    def _account(m: re.Match) -> str:
        _mark("account_number")
        return m.group(1) + "[ACCOUNT REDACTED]"

    def _cred(m: re.Match) -> str:
        _mark("credential")
        return m.group(1) + " [REDACTED]"

    masked = CARD_RE.sub(_card, text)
    masked = NRC_RE.sub(_nrc, masked)
    masked = ACCOUNT_RE.sub(_account, masked)
    masked = CRED_ASSIGN_RE.sub(_cred, masked)
    masked = CRED_DIGITS_RE.sub(_cred, masked)
    return masked, findings


def urgent_scan(text: str):
    """Return ("fraud", "lost_card"|"fraud") or ("complaint", None) or None."""
    t = " ".join((text or "").lower().split())
    if not t:
        return None
    if any(p in t for p in LOST_CARD_PHRASES):
        return ("fraud", "lost_card")
    if FRAUD_RE.search(t) or any(p in t for p in FRAUD_PHRASES):
        return ("fraud", "fraud")
    if COMPLAINT_RE.search(t) or any(p in t for p in COMPLAINT_PHRASES):
        return ("complaint", None)
    return None


def is_abusive(text: str) -> bool:
    return bool(ABUSE_RE.search(text or ""))

"""Input guards (§3.3): PII detect/mask, urgent-keyword scan, input hygiene.

Everything here runs BEFORE matching, flows, or logging — nothing downstream
(including the audit trail) ever sees unmasked PII.
"""

import re
from typing import NamedTuple

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

# The warning shown when PII is detected is msg("pii_warning") (C1).

# --- Urgent-topic scan (§3.1C, ticket S1) ---------------------------------
#
# Runs on EVERY message, in any flow state. Two strengths, because the cost of
# the two error kinds is not symmetric:
#
#   HARD  an unambiguous report of theft/fraud/a lost card. Goes straight into
#         the fraud flow and preempts any other in-progress flow. Missing one
#         of these is the worst outcome the bot can produce, so the bar is low.
#   SOFT  wording that is *consistent with* fraud or a complaint but has an
#         innocent reading at least as likely ("money gone", a bare mention of
#         the word "complaint"). These ask a confirmation question instead of
#         hijacking the conversation -- see router._urgent_confirmation().
#
# Before S1 every signal here was hard, which produced both misses ("they stole
# my money" was not matched at all) and false alarms (the bare substring "did
# not make" put "I didn't make it to the branch today" into the fraud flow).


class UrgentSignal(NamedTuple):
    """kind: "fraud"|"complaint" - sub: "lost_card"|"fraud"|None - strength."""

    kind: str
    sub: str | None
    strength: str  # "hard" | "soft"

    @property
    def is_hard(self) -> bool:
        return self.strength == "hard"


LOST_CARD_PHRASES = [
    "lost my card", "lost card", "card was stolen", "card stolen", "stolen card",
    "stollen card", "card missing", "missing card", "cant find my card",
    "can't find my card", "block my card", "card is gone", "stole my card",
    "cancel my card", "someone has my card", "card was taken", "took my card",
]
# The phrase list above is too literal on its own ("my card is missing" was
# missed): a card word within a few words of a loss/theft word also counts.
_LOSS = r"(?:lost|lose|misplaced|missing|stolen|stollen|gone|taken)"
LOST_CARD_RE = re.compile(
    rf"(?i)\b{_LOSS}\s+(?:\w+\s+){{0,2}}(?:atm\s+|debit\s+|visa\s+)?cards?\b"
    rf"|\bcards?\s+(?:\w+\s+){{0,2}}{_LOSS}\b"
)

# Unambiguous theft/fraud vocabulary, with the misspellings seen in real
# traffic. Word-bounded, so "stolen" matches and "stolenly" does not.
FRAUD_HARD_RE = re.compile(
    r"(?i)\b(?:scam\w*|skam\w*|fraud\w*|defraud\w*|"
    r"stole|stolen|stollen|stoled|steal|steals|stealing|steeling|"
    r"theft|thief|thieves|thieved|"
    r"hack\w*|unauthori[sz]\w*|conned|cheated|"
    r"phish\w*|skimm\w*|cloned|impersonat\w*|swindl\w*|duped)\b"
)

# Multi-word hard signals. These are the S1 misses: none of them contain a
# single word from FRAUD_HARD_RE, which is why the old scan returned None and
# the fuzzy matcher silently picked the lost-CARD intent for "someone stole
# money from my etumba" -- telling a customer to secure a card they never
# mentioned.
FRAUD_HARD_PHRASES = [
    "someone took", "somebody took", "they took my", "took my money",
    "took money from my account", "taken from my account", "money was taken",
    "money got taken", "taken without my permission", "without my permission",
    "without my consent", "without my knowledge", "without my authorisation",
    "without my authorization", "withdrew without", "withdrawn without",
    "did not authorise", "did not authorize", "didnt authorise",
    "didn't authorise", "didn't authorize", "never authorised",
    "never authorized", "someone accessed my account",
    "someone is using my account", "someone has access to my account",
    "someone logged into my account", "not my transaction",
    "transaction i did not make", "transactions i did not make",
    "debited without",
]

# Consistent with fraud, but with a plausible innocent reading -> confirm.
SOFT_MONEY_PHRASES = [
    "money gone", "money is gone", "money missing", "missing money",
    "money disappeared", "money has disappeared", "money vanished",
    "funds missing", "missing funds", "balance is wrong", "wrong balance",
    "balance is less", "less money in my account", "money not in my account",
    "money is not in my account", "money reduced", "account was debited",
]

# The old FRAUD_PHRASES entry was the bare substring "did not make", which
# fired on "I didn't make it to the branch" and "I did not make the deadline".
# It only counts when what was not made is a *transaction*.
SOFT_DID_NOT_MAKE_RE = re.compile(
    r"(?i)\b(?:did\s*not|didn'?t|didnt|never)\s+ma(?:k\w*|de)\b(?:\s+\w+){0,3}?\s+"
    r"(?:transactions?|payments?|withdrawals?|transfers?|deposits?|"
    r"purchases?|debits?|charges?)\b"
)

# Explicit intent to complain -> start the complaint flow directly, as before.
COMPLAINT_HARD_PHRASES = [
    "want to complain", "wish to complain", "like to complain",
    "need to complain", "make a complaint", "file a complaint",
    "lodge a complaint", "raise a complaint", "log a complaint",
    "submit a complaint", "formal complaint", "official complaint",
    "i am complaining", "i'm complaining", "im complaining",
    "poor service", "bad service", "terrible service", "worst service",
    "awful service", "not happy with", "very disappointed",
]
# A bare mention of the vocabulary -> confirm rather than assume.
COMPLAINT_SOFT_RE = re.compile(
    r"(?i)\b(?:complain\w*|compliant|disput\w*|unacceptable|rude|"
    r"disrespectful|appalling)\b"
)

# --- Negation -------------------------------------------------------------
#
# "I don't want to complain, just a question" opened a complaint before S1.
# Negation is matched adjacent to the signal word rather than anywhere in the
# sentence: "I didn't get an SMS and now my money is stolen" must stay hard.
NEGATED_FRAUD_RE = re.compile(
    r"(?i)\b(?:not|nothing\s+(?:was|is)|wasn'?t|isn'?t|ain'?t|no)\s+"
    r"(?:been\s+|a\s+|an\s+|any\s+)*"
    r"(?:stole|stolen|stollen|scam|scammed|fraud|fraudulent|hacked|defrauded)\b"
)
NEGATED_COMPLAINT_RE = re.compile(
    r"(?i)\b(?:do\s*n'?t|dont|do\s+not|does\s*n'?t|did\s*n'?t|not|never|no|"
    r"rather\s+not|prefer\s+not\s+to)\s+"
    r"(?:really\s+|just\s+|want\s+to\s+|wanna\s+|wish\s+to\s+|trying\s+to\s+|"
    r"going\s+to\s+|gonna\s+|mean\s+to\s+|a\s+|an\s+|any\s+)*"
    r"(?:complain\w*|compliant|dispute)\b"
)
# "is it rude to ask about fees" is a question about etiquette, not a report.
RUDE_QUESTION_RE = re.compile(
    r"(?i)\b(?:is|was|would|will|isn'?t|wouldn'?t)\s+it\s+(?:be\s+)?rude\b"
    r"|\bam\s+i\s+(?:being\s+)?rude\b|\bwas\s+i\s+rude\b"
)
NO_PROBLEM_RE = re.compile(r"(?i)\bno\s+(?:problem|worries|issue|complaints?)\b")
# "how do i protect myself from scams" is a question ABOUT fraud, not a
# report of it. Hijacking it into a fraud report is a false alarm, but
# ignoring it is not safe either, so it is downgraded to soft (ask first).
# "how do i report fraud" has none of these words and stays hard.
EDUCATION_RE = re.compile(
    r"(?i)^(?:how|what|which|where|can|could|is|are|any|tips?|ways?)\b.*\b(?:"
    r"protect\w*|avoid\w*|prevent\w*|spot|recogni[sz]e|identify|signs?\s+of|"
    r"tips?|safe|safety|aware|common|types?\s+of|kinds?\s+of|examples?\s+of|"
    r"charges?|fees?|costs?|replac\w*|how\s+long"
    r")\b"
)

# Card wording is only right when a card is actually mentioned (S1 change 3):
# "someone stole money from my eTumba" must get the money-theft intro.
CARD_MENTION_RE = re.compile(r"(?i)\b(?:card|cards|visa|mastercard)\b")

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


def _fraud_sub(t: str) -> str:
    """Card-block intro only if a card was actually mentioned (S1 change 3)."""
    return "lost_card" if CARD_MENTION_RE.search(t) else "fraud"


def urgent_negated(text: str) -> bool:
    """True when the message explicitly says it is NOT fraud/a complaint.
    The router then keeps the matcher from starting those flows either."""
    t = " ".join((text or "").lower().split())
    return bool(
        NEGATED_FRAUD_RE.search(t) or NEGATED_COMPLAINT_RE.search(t)
        or NO_PROBLEM_RE.search(t)
    )


def urgent_scan(text: str) -> UrgentSignal | None:
    """Classify a message for urgent routing. See the module comment above."""
    t = " ".join((text or "").lower().split())
    if not t:
        return None

    # 1. Hard fraud. Negation only suppresses when it sits directly on the
    # signal word ("nothing was stolen"); anything looser keeps the report.
    if not NEGATED_FRAUD_RE.search(t):
        if any(p in t for p in LOST_CARD_PHRASES) or LOST_CARD_RE.search(t):
            strength = "soft" if EDUCATION_RE.search(t) else "hard"
            return UrgentSignal("fraud", "lost_card", strength)
        if FRAUD_HARD_RE.search(t) or any(p in t for p in FRAUD_HARD_PHRASES):
            strength = "soft" if EDUCATION_RE.search(t) else "hard"
            return UrgentSignal("fraud", _fraud_sub(t), strength)

    complaint_negated = bool(
        NEGATED_COMPLAINT_RE.search(t) or NO_PROBLEM_RE.search(t)
    )

    # 2. Explicit intent to complain still starts the complaint flow directly.
    if not complaint_negated and any(p in t for p in COMPLAINT_HARD_PHRASES):
        return UrgentSignal("complaint", None, "hard")

    # 3. Soft money signals -> confirmation question.
    if not NO_PROBLEM_RE.search(t):
        if any(p in t for p in SOFT_MONEY_PHRASES) or SOFT_DID_NOT_MAKE_RE.search(t):
            return UrgentSignal("fraud", _fraud_sub(t), "soft")

    # 4. Soft complaint vocabulary -> confirmation question.
    if not complaint_negated and not RUDE_QUESTION_RE.search(t):
        if COMPLAINT_SOFT_RE.search(t):
            return UrgentSignal("complaint", None, "soft")

    return None


YES_WORDS = frozenset({
    "yes", "y", "yeah", "yea", "yep", "yup", "yes please", "please", "ok",
    "okay", "sure", "correct", "right", "thats right", "that's right", "ehe",
    "eya", "yes it is", "it is", "of course", "go ahead", "yes report it",
})
NO_WORDS = frozenset({
    "no", "n", "nope", "nah", "no thanks", "no thank you", "not really",
    "thats all", "that's all", "no its not", "no it's not", "it isnt",
    "it isn't", "no i have a question", "i have a question", "ayi", "iyo",
})
_PUNCT_RE = re.compile(r"[^\w\s']+")


def normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace -- for whole-message
    comparisons (commands, yes/no). Never used for matching or storage."""
    return " ".join(_PUNCT_RE.sub(" ", (text or "").lower()).split())


def yes_no(text: str) -> bool | None:
    """True/False for a whole-message yes or no, else None."""
    t = normalise(text)
    if t in YES_WORDS:
        return True
    if t in NO_WORDS:
        return False
    return None


def is_abusive(text: str) -> bool:
    return bool(ABUSE_RE.search(text or ""))

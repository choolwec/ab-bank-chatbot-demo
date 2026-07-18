"""Per-message pipeline (§3.2): guards → flows → matcher → response.

Design rules enforced here (§1): no dead ends (every response carries at
least one button), two-strike fallback, urgent topics bypass everything,
PII masked before anything else sees the text.
"""

from . import audit, config, guards
from .flows import FLOWS
from .matcher import Matcher

matcher = Matcher()

MENU_BUTTONS = [
    {"label": "Branches & agents", "payload": "branch_locator"},
    {"label": "Open an account", "payload": "account_types_overview"},
    {"label": "eTumba", "payload": "etumba_what_is"},
    {"label": "Loans", "payload": "msme_loan"},
    {"label": "Talk to a person", "payload": "human_handoff"},
]
DEFAULT_BUTTONS = [
    {"label": "Main menu", "payload": "menu"},
    {"label": "Talk to a person", "payload": "human_handoff"},
]

# §3.4 draft welcome — discloses automation, states capability, human option
WELCOME_TEXT = (
    "Hello! I'm the AB Bank assistant — an automated helper, not a person. "
    "I can help with branches and agents, opening an account, eTumba, and "
    "loans, or connect you to our team. What can I help with?"
)
FALLBACK_TEXT = (
    "I didn't quite catch that. You can try different words, pick an option "
    "below, or ask for a person at any time."
)
TWO_STRIKE_TEXT = (
    "I'm sorry — I'm not getting this right. Rather than keep guessing, let "
    "me connect you with a person who can help."
)
ABUSE_TEXT = (
    "I can hear this is frustrating — I'm sorry. Let me connect you with a "
    "person who can sort it out properly."
)


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _render(text: str) -> str:
    try:
        return text.format_map(_SafeDict(config.CONTACTS))
    except (ValueError, IndexError):
        return text


def welcome(session):
    session.greeted = True
    session.active_flow = None
    session.flow_state = {}
    replies = [{"text": WELCOME_TEXT, "buttons": list(MENU_BUTTONS)}]
    session.add("bot", WELCOME_TEXT)
    audit.log_event(session.id, "bot", WELCOME_TEXT, action="welcome")
    return replies


def handle(session, text=None, payload=None):
    """Full pipeline for one inbound message. Returns (replies, meta)."""
    cleaned = guards.clean(text) if text else ""
    masked, findings = guards.mask(cleaned)
    inbound = masked if text else f"[button] {payload}"
    session.add("user", inbound)
    audit.log_event(session.id, "user", inbound)

    replies = []
    if findings:
        replies.append({"text": guards.PII_WARNING, "buttons": []})

    routed, meta = _route(session, masked if text else None, payload)
    replies.extend(routed)

    # No dead ends, ever (§1 rule 1)
    if not replies:
        replies = [{"text": FALLBACK_TEXT, "buttons": list(MENU_BUTTONS)}]
    if not replies[-1].get("buttons"):
        replies[-1]["buttons"] = list(DEFAULT_BUTTONS)

    for reply in replies:
        reply["text"] = _render(reply["text"])
        session.add("bot", reply["text"])
        audit.log_event(
            session.id,
            "bot",
            reply["text"],
            intent=meta.get("intent"),
            confidence=meta.get("confidence"),
            action=meta.get("action"),
        )
    return replies, meta


def _route(session, text, payload):
    # 0. Session controls come before everything
    if payload in ("menu", "start"):
        session.active_flow = None
        session.flow_state = {}
        return (
            [{"text": "What can I help with?", "buttons": list(MENU_BUTTONS)}],
            {"action": "menu"},
        )
    if payload == "cancel_flow":
        session.active_flow = None
        session.flow_state = {}
        return (
            [{"text": "No problem — back to the main menu.", "buttons": list(MENU_BUTTONS)}],
            {"action": "cancel"},
        )
    # "Talk to a person" always works, even mid-flow (§1 rule 1)
    if payload == "human_handoff":
        session.strikes = 0
        replies, done = FLOWS["lead"].start(session)
        if done:
            session.active_flow = None
        return replies, {"intent": "human_handoff", "action": "flow_start"}

    # 1. Urgent topics bypass everything, from any flow (§1 rule 3)
    if text:
        urgent = guards.urgent_scan(text)
        if urgent and session.active_flow not in ("fraud", "complaint"):
            kind, sub = urgent
            session.strikes = 0
            flow = FLOWS["fraud" if kind == "fraud" else "complaint"]
            replies, done = flow.start(session, kind=sub)
            if done:
                session.active_flow = None
            return replies, {"action": f"urgent:{kind}"}

    # 2. An active flow consumes the message
    if session.active_flow:
        flow = FLOWS[session.active_flow]
        replies, done = flow.handle(session, text or "", payload)
        if done:
            session.active_flow = None
            session.flow_state = {}
        return replies, {"action": f"flow:{flow.name}"}

    # 3. Quick-reply payload → direct intent
    if payload:
        intent = matcher.get(payload)
        if intent:
            return _answer(session, intent, 1.0)
        return (
            [{"text": FALLBACK_TEXT, "buttons": list(MENU_BUTTONS)}],
            {"action": "unknown_payload"},
        )

    if not text:
        return (
            [{"text": "What can I help with?", "buttons": list(MENU_BUTTONS)}],
            {"action": "menu"},
        )

    # 4. Abuse/frustration → calm + human, no lecture
    if guards.is_abusive(text):
        return (
            [
                {
                    "text": ABUSE_TEXT,
                    "buttons": [
                        {"label": "Request a callback", "payload": "human_handoff"},
                        {"label": "Main menu", "payload": "menu"},
                    ],
                }
            ],
            {"action": "abuse"},
        )

    # 5. Free text → matcher (kill switch: menu-only mode, §3.3)
    if not config.free_text_enabled():
        return (
            [
                {
                    "text": "Free-typing is temporarily unavailable — please "
                    "choose an option below.",
                    "buttons": list(MENU_BUTTONS),
                }
            ],
            {"action": "freetext_off"},
        )

    ranked = matcher.match(text)
    top_name, top_score = ranked[0] if ranked else (None, 0.0)

    if top_name and top_score >= config.HIGH_CONFIDENCE:
        return _answer(session, matcher.get(top_name), top_score)

    if top_name and top_score >= config.MEDIUM_CONFIDENCE:
        buttons = [
            {"label": matcher.get(name).get("label", name), "payload": name}
            for name, score in ranked[: config.SUGGESTION_COUNT]
            if score >= config.MEDIUM_CONFIDENCE
        ]
        buttons.append({"label": "Talk to a person", "payload": "human_handoff"})
        return (
            [
                {
                    "text": "I want to make sure I get this right — did you "
                    "mean one of these?",
                    "buttons": buttons,
                }
            ],
            {"action": "did_you_mean", "confidence": round(top_score, 3)},
        )

    # Low confidence = a strike (§1 rule 2)
    session.strikes += 1
    audit.log_event(session.id, "system", text, action="unmatched")
    if session.strikes >= 2:
        session.strikes = 0
        return (
            [
                {
                    "text": TWO_STRIKE_TEXT,
                    "buttons": [
                        {"label": "Request a callback", "payload": "human_handoff"},
                        {"label": "Main menu", "payload": "menu"},
                    ],
                }
            ],
            {"action": "two_strike", "confidence": round(top_score, 3)},
        )
    return (
        [{"text": FALLBACK_TEXT, "buttons": list(MENU_BUTTONS)}],
        {"action": "fallback", "confidence": round(top_score, 3)},
    )


def _answer(session, intent, score):
    session.strikes = 0
    meta = {"intent": intent["intent"], "confidence": round(float(score), 3)}

    flow_name = intent.get("flow")
    if flow_name:
        kind = (intent.get("flow_args") or {}).get("kind")
        replies, done = FLOWS[flow_name].start(session, kind=kind)
        if done:
            session.active_flow = None
            session.flow_state = {}
        meta["action"] = "flow_start"
        return replies, meta

    session.slots["last_intent"] = intent["intent"]
    session.slots["topic"] = intent.get("category")
    answer = intent.get("answer")
    if not answer:
        return [{"text": FALLBACK_TEXT, "buttons": list(MENU_BUTTONS)}], meta
    buttons = [dict(b) for b in intent.get("buttons", [])]
    meta["action"] = "answer"
    return [{"text": answer.strip(), "buttons": buttons}], meta

"""Per-message pipeline (§3.2): guards → flows → matcher → response.

Design rules enforced here (§1): no dead ends (every response carries at
least one button), two-strike fallback, urgent topics bypass everything,
PII masked before anything else sees the text.
"""

from . import audit, config, guards
from .messages import msg
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

# S1 soft-urgent confirmation payloads. Wording: urgent_confirm.* in
# knowledge/system_messages.yaml (Ops/Risk reviews it).
URGENT_YES = "urgent_yes"
URGENT_NO = "urgent_no"
_URGENT_BUTTONS = {
    "fraud": "Yes, report it",
    "lost_card": "Yes, report it",
    "complaint": "Yes, complain",
}


def _urgent_confirm(kind, sub):
    key = sub if sub in _URGENT_BUTTONS else kind
    return {
        "text": msg(f"urgent_confirm.{key}"),
        "buttons": [
            {"label": _URGENT_BUTTONS[key], "payload": URGENT_YES},
            {"label": "No, I have a question", "payload": URGENT_NO},
        ],
    }


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
    text = _render(msg("welcome"))
    replies = [{"text": text, "buttons": list(MENU_BUTTONS)}]
    session.add("bot", text)
    audit.log_event(session.id, "bot", text, action="welcome")
    return replies


def resume(session):
    """A returning page load (widget reopened with a live session).

    Never resets state: a half-finished fraud/complaint/callback flow is
    re-prompted at its current step — only a human closes those (§1 rule 3).
    """
    if session.active_flow:
        flow = FLOWS[session.active_flow]
        replies = [{"text": msg("resume_flow"), "buttons": []}] + flow.resume(session)
        meta = {"action": "resume_flow"}
    else:
        replies = [{"text": msg("resume"), "buttons": list(MENU_BUTTONS)}]
        meta = {"action": "resume"}
    if not replies[-1].get("buttons"):
        replies[-1]["buttons"] = list(DEFAULT_BUTTONS)
    for reply in replies:
        reply["text"] = _render(reply["text"])
        session.add("bot", reply["text"])
        audit.log_event(session.id, "bot", reply["text"], action=meta["action"])
    return replies, meta


def handle(session, text=None, payload=None):
    """Full pipeline for one inbound message. Returns (replies, meta)."""
    cleaned = guards.clean(text) if text else ""
    masked, findings = guards.mask(cleaned)
    inbound = masked if text else f"[button] {payload}"
    session.add("user", inbound)
    audit.log_event(session.id, "user", inbound)

    replies = []
    if findings:
        replies.append({"text": msg("pii_warning"), "buttons": []})

    routed, meta = _route(session, masked if text else None, payload)
    replies.extend(routed)

    # No dead ends, ever (§1 rule 1)
    if not replies:
        replies = [{"text": msg("fallback"), "buttons": list(MENU_BUTTONS)}]
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
    # A soft-urgent confirmation question (S1) can only be answered by the
    # very next message -- anything else, including a button, drops it.
    pending = session.slots.pop("pending_urgent", None)

    # 0. Session controls come before everything
    if payload in ("menu", "start"):
        session.active_flow = None
        session.flow_state = {}
        return (
            [{"text": msg("menu"), "buttons": list(MENU_BUTTONS)}],
            {"action": "menu"},
        )
    if payload == "cancel_flow":
        session.active_flow = None
        session.flow_state = {}
        return (
            [{"text": msg("cancelled"), "buttons": list(MENU_BUTTONS)}],
            {"action": "cancel"},
        )
    # "Talk to a person" always works, even mid-flow (§1 rule 1)
    if payload == "human_handoff":
        session.strikes = 0
        replies, done = FLOWS["lead"].start(session)
        if done:
            session.active_flow = None
        return replies, {"intent": "human_handoff", "action": "flow_start"}

    # 1a. Answer to that confirmation question
    if payload in (URGENT_YES, URGENT_NO):
        if pending:
            return _resolve_urgent(session, pending, confirmed=payload == URGENT_YES)
        # A stale button from an old reply: harmless, and never wipes a flow.
        if session.active_flow:
            return FLOWS[session.active_flow].resume(session), {"action": "stale_button"}
        return (
            [{"text": msg("stale_button"), "buttons": list(MENU_BUTTONS)}],
            {"action": "stale_button"},
        )
    if pending and text:
        answer = guards.yes_no(text)
        if answer is not None:
            return _resolve_urgent(session, pending, confirmed=answer)

    # 1b. Urgent topics bypass everything, from any flow (§1 rule 3)
    if text:
        urgent = guards.urgent_scan(text)
        if urgent and session.active_flow not in ("fraud", "complaint"):
            if urgent.is_hard:
                return _start_urgent(session, urgent.kind, urgent.sub)
            # Soft: ask first. The flow state is left untouched, so "no"
            # resumes whatever the customer was doing.
            return _ask_urgent(session, urgent.kind, urgent.sub, text, source="scan")

    # 2. An active flow consumes the message — unless it's a high-confidence
    # unrelated FAQ question, in which case answer it and resume the flow at
    # the same step rather than trying to shoehorn it into the current field
    # (§ pattern from RasaHQ/financial-demo's "switch skills mid-transaction
    # and return"). Only applies to free-text, unvalidated steps, so fields
    # with their own retry logic (e.g. phone numbers) are untouched.
    if session.active_flow:
        flow = FLOWS[session.active_flow]
        if text and not payload:
            interrupt = _maybe_answer_faq_interrupt(flow, session, text)
            if interrupt is not None:
                return interrupt, {"action": f"flow_interrupt:{flow.name}"}
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
            [{"text": msg("fallback"), "buttons": list(MENU_BUTTONS)}],
            {"action": "unknown_payload"},
        )

    if not text:
        return (
            [{"text": msg("menu"), "buttons": list(MENU_BUTTONS)}],
            {"action": "menu"},
        )

    # 4. Abuse/frustration → calm + human, no lecture
    if guards.is_abusive(text):
        return (
            [
                {
                    "text": msg("abuse"),
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
                    "text": msg("freetext_off"),
                    "buttons": list(MENU_BUTTONS),
                }
            ],
            {"action": "freetext_off"},
        )

    return _free_text(session, text, urgent_flows=not guards.urgent_negated(text))


def _free_text(session, text, urgent_flows=True):
    """Matcher + confidence gate. `urgent_flows=False` is used after the
    customer has said "no, it's not fraud": an intent that would start the
    fraud/complaint flow anyway must not override their answer."""
    ranked = matcher.match(text)
    if not urgent_flows:
        ranked = [
            (n, s) for n, s in ranked
            if matcher.get(n).get("flow") not in ("fraud", "complaint")
        ]
    top_name, top_score = ranked[0] if ranked else (None, 0.0)

    if top_name and top_score >= config.HIGH_CONFIDENCE:
        intent = matcher.get(top_name)
        if intent.get("flow") in ("fraud", "complaint"):
            # The keyword scan already let this message through, so only the
            # fuzzy matcher calls it urgent ("i am happy with the service" is
            # close to "not happy with the service"). Ask, don't hijack.
            kind = intent["flow"]
            sub = (intent.get("flow_args") or {}).get("kind")
            if sub == "lost_card" and not guards.CARD_MENTION_RE.search(text):
                sub = "fraud"
            return _ask_urgent(session, kind, sub, text, source="matcher")
        return _answer(session, intent, top_score, text=text)

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
                    "text": msg("did_you_mean"),
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
                    "text": msg("two_strike"),
                    "buttons": [
                        {"label": "Request a callback", "payload": "human_handoff"},
                        {"label": "Main menu", "payload": "menu"},
                    ],
                }
            ],
            {"action": "two_strike", "confidence": round(top_score, 3)},
        )
    return (
        [{"text": msg("fallback"), "buttons": list(MENU_BUTTONS)}],
        {"action": "fallback", "confidence": round(top_score, 3)},
    )


def _maybe_answer_faq_interrupt(flow, session, text):
    """Return replies if `text` is a high-confidence, unrelated FAQ question
    asked mid-flow, else None (let the flow handle it as normal).

    Trade-off, stated plainly: this is a heuristic, not true intent
    disambiguation. A HIGH_CONFIDENCE bar (the same one used for "answer
    directly" elsewhere) keeps false positives rare, and it only applies to
    fields a flow has explicitly opted into `interruptible_fields` — see
    that attribute's comment in flows/base.py for why most fields must NOT
    opt in.
    """
    state = session.flow_state
    steps = getattr(flow, "steps", None)
    if not steps or state.get("confirming"):
        return None
    i = state.get("step", 0)
    if i >= len(steps):
        return None
    field = steps[i]
    if field not in getattr(flow, "interruptible_fields", ()):
        return None

    ranked = matcher.match(text)
    top_name, top_score = ranked[0] if ranked else (None, 0.0)
    if not top_name or top_score < config.HIGH_CONFIDENCE:
        return None
    intent = matcher.get(top_name)
    if intent.get("flow") or not intent.get("answer"):
        return None

    prompt = flow._prompt(i)
    back = msg("back_to_flow", flow=flow.topic_label, prompt=prompt["text"])
    return [
        {
            "text": intent["answer"].strip() + "\n\n" + back,
            "buttons": prompt["buttons"],
        }
    ]


def _start_urgent(session, kind, sub):
    session.strikes = 0
    flow = FLOWS["fraud" if kind == "fraud" else "complaint"]
    replies, done = flow.start(session, kind=sub)
    if done:
        session.active_flow = None
    return replies, {"action": f"urgent:{kind}"}


def _ask_urgent(session, kind, sub, text, source):
    session.slots["pending_urgent"] = {"kind": kind, "sub": sub, "text": text}
    return (
        [_urgent_confirm(kind, sub)],
        {"action": f"urgent_confirm:{kind}", "urgent_source": source},
    )


def _resolve_urgent(session, pending, confirmed):
    if confirmed:
        return _start_urgent(session, pending["kind"], pending["sub"])
    # "No, I have a question": pick up an interrupted flow where it was, or
    # answer the original message -- minus the urgent reading they declined.
    if session.active_flow:
        flow = FLOWS[session.active_flow]
        return (
            [{"text": msg("urgent_declined_flow"), "buttons": []}] + flow.resume(session),
            {"action": "urgent_declined"},
        )
    strikes = session.strikes
    replies, meta = _free_text(session, pending["text"], urgent_flows=False)
    if meta.get("action") in ("fallback", "two_strike"):
        # Their message only read as urgent, so a strike would be unfair.
        session.strikes = strikes
        replies = [{"text": msg("urgent_declined"), "buttons": list(MENU_BUTTONS)}]
    meta = dict(meta, action="urgent_declined", declined_answer=meta.get("action"))
    return replies, meta


def _answer(session, intent, score, text=None):
    session.strikes = 0
    meta = {"intent": intent["intent"], "confidence": round(float(score), 3)}

    flow_name = intent.get("flow")
    if flow_name:
        kind = (intent.get("flow_args") or {}).get("kind")
        # Card-block wording only when a card was actually mentioned (S1).
        if kind == "lost_card" and text and not guards.CARD_MENTION_RE.search(text):
            kind = "fraud"
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
        return [{"text": msg("fallback"), "buttons": list(MENU_BUTTONS)}], meta
    buttons = [dict(b) for b in intent.get("buttons", [])]
    meta["action"] = "answer"
    return [{"text": answer.strip(), "buttons": buttons}], meta

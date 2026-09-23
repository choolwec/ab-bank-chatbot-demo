"""Per-message pipeline (§3.2): guards → flows → matcher → response.

Design rules enforced here (§1): no dead ends (every response carries at
least one button), two-strike fallback, urgent topics bypass everything,
PII masked before anything else sees the text.
"""

import copy
import re

from rapidfuzz import fuzz

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


# C2: typed commands, matched against the WHOLE normalised message only.
COMMANDS = {
    **dict.fromkeys(
        ["cancel", "stop", "never mind", "nevermind", "quit", "exit", "cancel that"],
        "cancel_flow",
    ),
    **dict.fromkeys(
        ["menu", "main menu", "start again", "start over", "restart", "0", "home"],
        "menu",
    ),
    **dict.fromkeys(
        [
            "agent", "human", "person", "a person", "talk to a person",
            "speak to a person", "speak to someone", "talk to someone",
            "talk to a human", "speak to a human", "customer care",
            "customer service", "real person", "talk to an agent",
            "speak to an agent",
        ],
        "human_handoff",
    ),
    "help": "help",
    # C4: repairing the bot's own turn. Never a strike.
    **dict.fromkeys(
        ["repeat", "repeat that", "say again", "say that again", "come again",
         "pardon", "sorry what", "what did you say"],
        "repeat",
    ),
    **dict.fromkeys(
        ["what do you mean", "what does that mean", "i don't understand",
         "i dont understand", "i do not understand", "explain", "explain that",
         "please explain", "explain please", "can you explain", "huh", "eh",
         "example", "for example", "an example", "meaning", "not clear",
         "i'm confused", "im confused", "confused", "simpler please",
         "in simple words", "say it simply"],
        "clarify",
    ),
}
# Words that are commands elsewhere but a legitimate answer inside a flow:
# the locator asks "a branch, or an eTumba agent?".
COMMAND_ANSWERS = {"locator": {"agent", "an agent"}}
CANCEL_YES = "cancel_yes"
CANCEL_NO = "cancel_no"


def _urgent_confirm(kind, sub):
    key = sub if sub in _URGENT_BUTTONS else kind
    return {
        "text": msg(f"urgent_confirm.{key}"),
        "buttons": [
            {"label": _URGENT_BUTTONS[key], "payload": URGENT_YES},
            {"label": "No, I have a question", "payload": URGENT_NO},
        ],
        "yes": URGENT_YES,
        "no": URGENT_NO,
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
    _remember_expecting(session, replies, {"action": "welcome"})
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
    _remember_expecting(session, replies, meta)
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
    _remember_expecting(session, replies, meta)
    return replies, meta


# --- C3: answers to the bot's own questions -----------------------------------
# Buttons that are ways out rather than answers; they don't make a reply
# "a question with options" on their own.
_CONTROL_PAYLOADS = {"cancel_flow"}
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
}
_NUMBER_RE = re.compile(r"^(?:(?:option|number|no)\s*)?([1-9])$")
LABEL_MATCH_MIN = 90


def _remember_expecting(session, replies, meta=None):
    """Store what the final reply asked for (C3) and the replies themselves
    for "repeat" (C4); then strip the internal yes/no keys so they never
    reach the widget."""
    action = (meta or {}).get("action")
    if action != "repeat":
        session.last_replies = copy.deepcopy(replies)  # keeps yes/no for a repeat
    if action not in ("repeat", "clarify"):
        session.last_answer_intent = (meta or {}).get("intent") if action == "answer" else None
    last = replies[-1] if replies else {}
    session.expecting = {
        "options": [(b["label"], b["payload"]) for b in last.get("buttons", [])],
        "yes": last.get("yes"),
        "no": last.get("no"),
    }
    for reply in replies:
        reply.pop("yes", None)
        reply.pop("no", None)


def _expected_payload(expecting, text):
    """The payload `text` picks from the last reply, or None."""
    if not expecting:
        return None
    answer = guards.yes_no(text)
    if answer is True and expecting.get("yes"):
        return expecting["yes"]
    if answer is False and expecting.get("no"):
        return expecting["no"]
    options = expecting.get("options") or []
    if sum(p not in _CONTROL_PAYLOADS for _, p in options) < 2:
        return None  # a free-text step: "2" is an answer, not a pick
    t = guards.normalise(text)
    m = _NUMBER_RE.match(t)
    n = int(m.group(1)) if m else _NUMBER_WORDS.get(t)
    if n:
        return options[n - 1][1] if n <= len(options) else None
    best, best_score = None, 0
    for label, payload in options:
        score = fuzz.ratio(t, guards.normalise(label))
        if score > best_score:
            best, best_score = payload, score
    return best if best_score >= LABEL_MATCH_MIN else None


def _route(session, text, payload):
    # A soft-urgent confirmation question (S1) can only be answered by the
    # very next message -- anything else, including a button, drops it.
    pending = session.slots.pop("pending_urgent", None)
    # Same for what the last reply was expecting (C3).
    expecting = session.expecting
    session.expecting = {}

    # 0. Session controls come before everything
    if payload in ("menu", "start"):
        session.active_flow = None
        session.flow_state = {}
        return (
            [{"text": msg("menu"), "buttons": list(MENU_BUTTONS)}],
            {"action": "menu"},
        )
    if payload == "cancel_flow" or payload == CANCEL_YES:
        # Abandoning a fraud report or complaint is costly: confirm first (C2).
        if (
            payload == "cancel_flow"
            and session.active_flow in ("fraud", "complaint")
            and not session.flow_state.get("confirm_cancel")
        ):
            return _confirm_cancel(session)
        session.active_flow = None
        session.flow_state = {}
        return (
            [{"text": msg("cancelled"), "buttons": list(MENU_BUTTONS)}],
            {"action": "cancel"},
        )
    if payload == CANCEL_NO:
        return _continue_flow(session)
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

    # 1c. Typed commands work anywhere, exactly like their buttons (C2). Whole
    # message only: "cancel my card" is a lost-card report, caught above.
    if text and not payload:
        command = _typed_command(session, text)
        if command == "help":
            return _help(session)
        if command == "repeat":
            return _repeat(session)
        if command == "clarify":
            return _clarify(session)
        if command:
            if command == "menu" and session.active_flow in ("fraud", "complaint"):
                command = "cancel_flow"  # never drop a report without asking
            return _route(session, None, command)

    # 1c'. "yes", "2", or a typed button label answering the last reply (C3).
    if text and not payload:
        picked = _expected_payload(expecting, text)
        if picked:
            replies, meta = _route(session, None, picked)
            return replies, dict(meta, expected_pick=picked)

    # 1d. Answer to "Your report isn't sent yet. Stop anyway?"
    if session.active_flow and session.flow_state.pop("confirm_cancel", False) and text:
        answer = guards.yes_no(text)
        if answer is True:
            return _route(session, None, CANCEL_YES)
        if answer is False:
            return _continue_flow(session)
        # Anything else: they carried on with the report -- treat it as input.

    # 2. An active flow consumes the message — unless it's a high-confidence
    # unrelated FAQ question, in which case answer it and resume the flow at
    # the same step rather than trying to shoehorn it into the current field
    # (§ pattern from RasaHQ/financial-demo's "switch skills mid-transaction
    # and return"). Only applies to free-text, unvalidated steps, so fields
    # with their own retry logic (e.g. phone numbers) are untouched.
    if session.active_flow:
        flow = FLOWS[session.active_flow]
        if text and not payload:
            # Frustration mid-callback or mid-lookup: apologise, re-ask the
            # step (C5). Never inside a fraud report or complaint -- there,
            # "you people are not helping" IS the customer's account.
            if (
                flow.name not in ("fraud", "complaint")
                and guards.frustration_kind(text) == "phrase"
            ):
                return _frustrated(session, "phrase", flow=flow)
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

    # 4. Abuse/frustration → calm + human, no lecture. A frustration phrase
    # ("useless bot") gets the gentler reply even if a word is also on the
    # abuse list; swearing gets the abuse reply.
    frustration = guards.frustration_kind(text)
    if frustration == "phrase" and not guards.is_profane(text):
        return _frustrated(session, frustration)
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
    if frustration and (frustration != "caps" or not _confident(text)):
        return _frustrated(session, frustration)

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


def _typed_command(session, text):
    command = COMMANDS.get(guards.normalise(text))
    if command and guards.normalise(text) in COMMAND_ANSWERS.get(session.active_flow, ()):
        return None  # a legitimate answer to the current question
    return command


def _repeat(session):
    """Resend the last replies exactly; flow state is untouched."""
    if not session.last_replies:
        return [{"text": msg("menu"), "buttons": list(MENU_BUTTONS)}], {"action": "repeat"}
    return copy.deepcopy(session.last_replies), {"action": "repeat"}


def _clarify(session):
    """ "What do you mean?": the plainer answer_simple of the last answer,
    or the last message again with a way to a person."""
    intent = matcher.get(session.last_answer_intent) if session.last_answer_intent else None
    if intent and intent.get("answer_simple"):
        buttons = [dict(b) for b in intent.get("buttons", [])]
        return (
            [{"text": intent["answer_simple"].strip(), "buttons": buttons}],
            {"action": "clarify", "intent": intent["intent"]},
        )
    replies, _ = _repeat(session)
    last = replies[-1]
    if not any(b["payload"] == "human_handoff" for b in last.get("buttons", [])):
        last["buttons"] = list(last.get("buttons", [])) + [
            {"label": "Talk to a person", "payload": "human_handoff"}
        ]
    return replies, {"action": "clarify"}


def _confident(text):
    ranked = matcher.match(text)
    return bool(ranked) and ranked[0][1] >= config.HIGH_CONFIDENCE


def _frustrated(session, kind, flow=None):
    """Calm, an apology and a person (C5). Never a strike; logged as
    action=frustration so the weekly report can grow the phrase list."""
    human = {"label": "Talk to a person", "payload": "human_handoff"}
    if flow is not None:
        prompt = flow.resume(session)[-1]
        back = msg("back_to_flow", flow=flow.topic_label, prompt=prompt["text"])
        buttons = [human] + [b for b in prompt["buttons"] if b["payload"] != "human_handoff"]
        return (
            [{"text": msg("frustration") + "\n\n" + back, "buttons": buttons}],
            {"action": "frustration", "frustration": kind},
        )
    return (
        [{"text": msg("frustration"), "buttons": [human, {"label": "Main menu", "payload": "menu"}]}],
        {"action": "frustration", "frustration": kind},
    )


def _help(session):
    capabilities = matcher.get("bot_capabilities")["answer"].strip()
    if session.active_flow:
        flow = FLOWS[session.active_flow]
        prompt = flow.resume(session)[-1]
        back = msg("back_to_flow", flow=flow.topic_label, prompt=prompt["text"])
        return (
            [{"text": capabilities + "\n\n" + back, "buttons": prompt["buttons"]}],
            {"action": "help"},
        )
    return [{"text": capabilities, "buttons": list(MENU_BUTTONS)}], {"action": "help"}


def _confirm_cancel(session):
    session.flow_state["confirm_cancel"] = True
    flow = FLOWS[session.active_flow]
    return (
        [
            {
                "text": msg("cancel_confirm", flow=flow.topic_label),
                "buttons": [
                    {"label": "Yes, stop", "payload": CANCEL_YES},
                    {"label": "No, continue", "payload": CANCEL_NO},
                ],
                "yes": CANCEL_YES,
                "no": CANCEL_NO,
            }
        ],
        {"action": "cancel_confirm"},
    )


def _continue_flow(session):
    session.flow_state.pop("confirm_cancel", None)
    if not session.active_flow:
        return _route(session, None, "menu")
    flow = FLOWS[session.active_flow]
    return (
        [{"text": msg("carry_on"), "buttons": []}] + flow.resume(session),
        {"action": "cancel_declined"},
    )


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
    reply = {"text": answer.strip(), "buttons": buttons}
    # An answer that ends in a yes/no question declares what each means (C3).
    if intent.get("on_yes"):
        reply["yes"] = intent["on_yes"]
    if intent.get("on_no"):
        reply["no"] = intent["on_no"]
    return [reply], meta

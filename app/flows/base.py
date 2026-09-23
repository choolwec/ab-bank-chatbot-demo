"""Shared flow machinery: a simple step-form state machine.

A flow returns (replies, done). Replies are dicts: {"text": str, "buttons":
[{"label","payload"}]}. The router guarantees the last reply always carries
at least one button (no dead ends, §1 rule 1).
"""

import re

CANCEL_BUTTON = {"label": "Back to menu", "payload": "cancel_flow"}
MENU_BUTTON = {"label": "Main menu", "payload": "menu"}
HUMAN_BUTTON = {"label": "Talk to a person", "payload": "human_handoff"}
# Reuses the thanks_goodbye intent as a button target (same pattern as
# HUMAN_BUTTON reusing human_handoff) so "is there anything else?" has an
# unambiguous answer instead of relying on free-text "no" detection alone.
DONE_BUTTON = {"label": "No, that's all", "payload": "thanks_goodbye"}

# Zambian mobile numbers: 0XXXXXXXXX (10 digits), 260XXXXXXXXX (12 digits,
# country code no plus), or +260XXXXXXXXX. Spaces/dashes are stripped first
# so "0977 123 456" and "0977-123-456" also pass.
PHONE_RE = re.compile(r"^(?:0\d{9}|260\d{9}|\+260\d{9})$")


def is_valid_zambian_phone(text: str) -> bool:
    cleaned = re.sub(r"[ \-]", "", text or "")
    return bool(PHONE_RE.fullmatch(cleaned))


def clean_phone(text: str) -> str:
    return re.sub(r"[ \-]", "", text or "")


def format_phone(text: str) -> str:
    """Read-back form of a valid Zambian number: '0977 123 456'."""
    digits = re.sub(r"\D", "", text or "")
    if digits.startswith("260") and len(digits) == 12:
        digits = "0" + digits[3:]
    if len(digits) == 10:
        return f"{digits[:4]} {digits[4:7]} {digits[7:]}"
    return text


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)


def is_valid_email(text: str) -> bool:
    return bool(EMAIL_RE.fullmatch((text or "").strip()))


SKIP_WORDS = frozenset({"skip", "no", "none", "no thanks", "rather not", "i'd rather not"})


def is_skip(text: str) -> bool:
    return " ".join((text or "").lower().strip(" .!").split()) in SKIP_WORDS


CONFIRM_BUTTON = {"label": "Yes, submit", "payload": "confirm_yes"}
EDIT_BUTTON = {"label": "No, let me fix that", "payload": "confirm_edit"}


class FormFlow:
    name = "form"
    # Human-readable noun used in "back to your {topic_label}" resume prompts
    # (§ mid-flow FAQ interrupt, see router._maybe_answer_faq_interrupt).
    topic_label = "request"
    # list of (field_key, prompt_text)
    steps: list[tuple[str, str]] = []
    # optional {field_key: (is_valid_fn, retry_message)} — checked before a
    # step's answer is stored; on failure the same step re-prompts with the
    # retry message instead of advancing.
    validators: dict[str, tuple] = {}
    # Fields where a mid-flow FAQ question is safe to detect (router.py's
    # _maybe_answer_faq_interrupt) — opt-in, not opt-out. Only genuinely
    # free-narrative fields belong here: fields whose *legitimate* answers
    # are themselves bank-topic words (e.g. fraud's "channel": card/eTumba/
    # branch, or lead's "topic") collide with the exact FAQ vocabulary this
    # check looks for, so those must stay excluded — confirmed the hard way
    # when "eTumba" as a channel answer and "Opening a business account" as
    # a callback topic were both misread as FAQ interruptions in testing.
    interruptible_fields: frozenset[str] = frozenset()
    # Flows that create a ticket/callback should confirm the collected data
    # before submitting it — a typo'd date or garbled detail otherwise goes
    # straight to a human with no chance to fix it. Read-only lookups (e.g.
    # the branch locator) leave this False.
    require_confirmation = False

    def intro(self, session, kind):
        return []

    def start(self, session, kind=None):
        session.active_flow = self.name
        session.flow_state = {"step": 0, "data": {}, "kind": kind}
        replies = self.intro(session, kind)
        replies.append(self._prompt(0))
        return replies, False

    def _prompt(self, i):
        return {"text": self.steps[i][1], "buttons": [CANCEL_BUTTON]}

    def _confirmation_prompt(self, session):
        data = session.flow_state.get("data", {})
        lines = [
            f"- {field.replace('_', ' ').capitalize()}: {data[field]}"
            for field, _ in self.steps
            if data.get(field)
        ]
        text = (
            "Here's what I've got:\n" + "\n".join(lines) + "\n\nShall I submit this?"
        )
        return {"text": text, "buttons": [CONFIRM_BUTTON, EDIT_BUTTON, CANCEL_BUTTON]}

    def resume(self, session):
        """Re-issue the current step's prompt without touching collected data.

        Used when a returning page load reopens an in-progress flow — a
        half-finished fraud report must never be silently discarded.
        """
        if session.flow_state.get("confirming"):
            return [self._confirmation_prompt(session)]
        i = min(session.flow_state.get("step", 0), len(self.steps) - 1)
        return [self._prompt(i)]

    def store_value(self, field, value):
        """Hook: the value stored for `field` (e.g. a canonical "skipped")."""
        return value

    def acknowledge(self, field, value):
        """Hook: optional read-back text sent before the next prompt."""
        return None

    def handle(self, session, text, payload=None):
        state = session.flow_state

        if state.get("confirming"):
            if payload == "confirm_yes":
                return self.finish(session), True
            if payload == "confirm_edit":
                last_field = self.steps[-1][0]
                state.get("data", {}).pop(last_field, None)
                state["step"] = len(self.steps) - 1
                state["confirming"] = False
                return [self._prompt(state["step"])], False
            # Unexpected free text while confirming: re-ask, no dead end.
            return [self._confirmation_prompt(session)], False

        i = state.get("step", 0)
        field = self.steps[i][0]
        value = (text or payload or "").strip()

        validator = self.validators.get(field)
        if validator:
            is_valid, retry_text = validator
            if not is_valid(value):
                return [{"text": retry_text, "buttons": [CANCEL_BUTTON]}], False

        value = self.store_value(field, value)
        state.setdefault("data", {})[field] = value
        ack = self.acknowledge(field, value)
        before = [{"text": ack, "buttons": []}] if ack else []
        i += 1
        state["step"] = i
        if i < len(self.steps):
            return before + [self._prompt(i)], False
        if self.require_confirmation:
            state["confirming"] = True
            return before + [self._confirmation_prompt(session)], False
        return before + self.finish(session), True

    def finish(self, session):
        raise NotImplementedError

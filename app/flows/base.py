"""Shared flow machinery: a simple step-form state machine.

A flow returns (replies, done). Replies are dicts: {"text": str, "buttons":
[{"label","payload"}]}. The router guarantees the last reply always carries
at least one button (no dead ends, §1 rule 1).

All wording comes from knowledge/system_messages.yaml (ticket C1), by
convention: "<flow>.step.<field>" for each prompt, "<flow>.retry.<field>" for
each validator's retry text, "<flow>.topic_label", and "field.<field>" for the
confirmation summary. flows/__init__.py checks every one exists at import.
"""

import re

from ..messages import msg

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
    # Field names, in order. Prompt wording: msg("<name>.step.<field>").
    steps: list[str] = []
    # optional {field: is_valid_fn} -- checked before a step's answer is
    # stored; on failure the same step re-prompts with msg("<name>.retry.<field>")
    # instead of advancing.
    validators: dict = {}
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

    @property
    def topic_label(self) -> str:
        """Noun used in "back to your {topic_label}" prompts."""
        return msg(f"{self.name}.topic_label")

    def message_keys(self) -> list[str]:
        """Every system-message key this flow looks up by convention."""
        keys = [f"{self.name}.topic_label"]
        keys += [f"{self.name}.step.{f}" for f in self.steps]
        keys += [f"{self.name}.retry.{f}" for f in self.validators]
        if self.require_confirmation:
            keys += [f"field.{f}" for f in self.steps]
        return keys

    def intro(self, session, kind):
        return []

    def start(self, session, kind=None):
        session.active_flow = self.name
        session.flow_state = {"step": 0, "data": {}, "kind": kind}
        replies = self.intro(session, kind)
        replies.append(self._prompt(0))
        return replies, False

    def _prompt(self, i):
        return {"text": msg(f"{self.name}.step.{self.steps[i]}"), "buttons": [CANCEL_BUTTON]}

    def _confirmation_prompt(self, session):
        data = session.flow_state.get("data", {})
        lines = "\n".join(
            f"- {msg(f'field.{field}')}: {data[field]}"
            for field in self.steps
            if data.get(field)
        )
        return {
            "text": msg("confirm.summary", lines=lines),
            "buttons": [CONFIRM_BUTTON, EDIT_BUTTON, CANCEL_BUTTON],
            "yes": CONFIRM_BUTTON["payload"],
            "no": EDIT_BUTTON["payload"],
        }

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
                last_field = self.steps[-1]
                state.get("data", {}).pop(last_field, None)
                state["step"] = len(self.steps) - 1
                state["confirming"] = False
                return [self._prompt(state["step"])], False
            # Unexpected free text while confirming: re-ask, no dead end.
            return [self._confirmation_prompt(session)], False

        i = state.get("step", 0)
        field = self.steps[i]
        value = (text or payload or "").strip()

        is_valid = self.validators.get(field)
        if is_valid and not is_valid(value):
            return [{"text": msg(f"{self.name}.retry.{field}"), "buttons": [CANCEL_BUTTON]}], False

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

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


# C6: a correction needs a marker AND a value that passes an earlier step's
# validator -- "sorry my number is actually 0966123456".
CORRECTION_RE = re.compile(
    r"(?i)\b(?:sorry|actually|i\s+meant|i\s+mean|wrong|correction|mistake|"
    r"typo|should\s+be|instead|not\s+\S+\s+but|"
    r"my\s+(?:number|phone|cell|mobile|email)\s+is|"
    r"change\s+(?:my|the)\s+(?:number|phone|email))\b"
)
PHONE_CANDIDATE_RE = re.compile(r"\+?\d[\d \-]{7,15}\d")
EMAIL_CANDIDATE_RE = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.IGNORECASE)


def value_candidates(text: str) -> list[str]:
    """Phone numbers and email addresses embedded in a longer message."""
    return PHONE_CANDIDATE_RE.findall(text or "") + EMAIL_CANDIDATE_RE.findall(text or "")


def read_back(value: str) -> str:
    return format_phone(value) if is_valid_zambian_phone(value) else value


def is_valid_contact(text: str) -> bool:
    """A phone number, an email address, or an explicit "skip"."""
    return is_valid_zambian_phone(text) or is_valid_email(text) or is_skip(text)


SKIPPED = "skipped"


def store_contact(value: str) -> str:
    if is_skip(value):
        return SKIPPED
    return clean_phone(value) if is_valid_zambian_phone(value) else value.strip()


SEND_BUTTON = {"label": "Send it", "payload": "confirm_yes"}
CHANGE_BUTTON = {"label": "Change something", "payload": "confirm_change"}
CHANGE_PREFIX = "change:"


def _with_ack(ack, reply):
    """Put a read-back ("Got it: 0977 123 456.") on the SAME bubble as the
    next prompt -- one message, not two (C7; the M1 message budget)."""
    if not ack:
        return reply
    return dict(reply, text=ack + "\n\n" + reply["text"])


class FormFlow:
    name = "form"
    # Field names, in order. Prompt wording: msg("<name>.step.<field>").
    steps: list[str] = []
    # optional {field: is_valid_fn} -- checked before a step's answer is
    # stored; on failure the same step re-prompts with msg("<name>.retry.<field>")
    # instead of advancing.
    validators: dict = {}

    # Fields a customer can correct later in the flow ("sorry, my number is
    # actually ...", C6). A correction is only recognised when the message
    # carries a value that passes the field's validator, so this defaults to
    # the validated fields; free-text fields can't be corrected this way.
    @property
    def correctable(self) -> frozenset[str]:
        return frozenset(self.validators)

    # Flows that create a ticket or callback show "Here's what I'll send" with
    # [Send it] [Change something] before finish() (C7), so a typo never goes
    # straight to a person. The fraud flow is the exception: speed over
    # polish, so its finish message shows the summary instead.
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
        keys += [f"field.{f}" for f in self.steps]
        return keys

    def intro(self, session, kind):
        return []

    def start(self, session, kind=None, trigger=None):
        """`trigger` is the customer message that started the flow, if any
        (a flow may pre-fill from it -- see FraudFlow)."""
        session.active_flow = self.name
        session.flow_state = {"step": 0, "data": {}, "kind": kind}
        return self.opening(session, self.intro(session, kind), self._prompt(0)), False

    def opening(self, session, intro, question):
        """The intro and the first question share ONE bubble (M1 budget)."""
        text = "\n\n".join([r["text"] for r in intro] + [question["text"]])
        return [dict(question, text=text)]

    def _prompt(self, i):
        return {"text": msg(f"{self.name}.step.{self.steps[i]}"), "buttons": [CANCEL_BUTTON]}

    def summary(self, session) -> str:
        """One line, values only: "Mary Banda · 0977 123 456 · a loan · Morning"."""
        data = session.flow_state.get("data", {})
        return " · ".join(read_back(str(data[f])) for f in self.steps if data.get(f))

    def _confirmation_prompt(self, session):
        return {
            "text": msg("confirm.summary", summary=self.summary(session)),
            "buttons": [SEND_BUTTON, CHANGE_BUTTON, CANCEL_BUTTON],
            "yes": SEND_BUTTON["payload"],
            "no": CHANGE_BUTTON["payload"],
        }

    def _change_prompt(self, session):
        data = session.flow_state.get("data", {})
        buttons = [
            {"label": msg(f"field.{f}"), "payload": CHANGE_PREFIX + f}
            for f in self.steps if f in data
        ]
        return {"text": msg("confirm.change"), "buttons": buttons + [SEND_BUTTON]}

    def resume(self, session):
        """Re-issue the current question without touching collected data.

        Used when a returning page load reopens an in-progress flow — a
        half-finished fraud report must never be silently discarded.
        """
        state = session.flow_state
        if state.get("editing"):
            return [self._prompt(self.steps.index(state["editing"]))]
        if state.get("changing"):
            return [self._change_prompt(session)]
        if state.get("confirming"):
            return [self._confirmation_prompt(session)]
        i = min(state.get("step", 0), len(self.steps) - 1)
        return [self._prompt(i)]

    def store_value(self, field, value):
        """Hook: the value stored for `field` (e.g. a canonical "skipped")."""
        return value

    def acknowledge(self, field, value):
        """Hook: optional read-back put in front of the next prompt."""
        return None

    def _correction(self, state, text):
        """(field, value) if `text` corrects an EARLIER answer, else None."""
        if not text or not CORRECTION_RE.search(text):
            return None
        current = len(self.steps) if state.get("confirming") else state.get("step", 0)
        data = state.get("data", {})
        for field in reversed(self.steps[:current]):
            is_valid = self.validators.get(field)
            if field not in self.correctable or not is_valid:
                continue
            for candidate in value_candidates(text):
                if is_valid(candidate):
                    value = self.store_value(field, candidate)
                    if data.get(field) != value:
                        return field, value
        return None

    def _apply_correction(self, session, field, value):
        state = session.flow_state
        state.setdefault("data", {})[field] = value
        label = msg(f"field.{field}").lower()
        note = msg("corrected", field=label, value=read_back(value))
        return [_with_ack(note, self.resume(session)[-1])], False

    def _validated(self, field, value):
        """(ok, value): the value to store, or ok=False to re-ask."""
        is_valid = self.validators.get(field)
        if not is_valid or is_valid(value):
            return True, value
        # "my number is 0977 123 456": use the one valid value inside.
        found = [c for c in value_candidates(value) if is_valid(c)]
        return (True, found[0]) if len(found) == 1 else (False, value)

    def _retry(self, field):
        return [{"text": msg(f"{self.name}.retry.{field}"), "buttons": [CANCEL_BUTTON]}], False

    def _handle_summary(self, session, text, payload):
        """At "Here's what I'll send" or the "which part?" question."""
        state = session.flow_state
        if payload == "confirm_yes":
            return self.finish(session), True
        if payload in ("confirm_change", "confirm_edit"):  # confirm_edit: pre-C7 buttons
            state["changing"] = True
            return [self._change_prompt(session)], False
        if payload and payload.startswith(CHANGE_PREFIX) and payload[len(CHANGE_PREFIX):] in self.steps:
            state.pop("changing", None)
            state["editing"] = payload[len(CHANGE_PREFIX):]
            return [self._prompt(self.steps.index(state["editing"]))], False
        # Anything else: ask the same question again, no dead end.
        return self.resume(session), False

    def handle(self, session, text, payload=None):
        state = session.flow_state

        correction = self._correction(state, text) if not payload else None
        if correction:
            state.pop("changing", None)
            state.pop("editing", None)
            return self._apply_correction(session, *correction)

        editing = state.get("editing")
        if editing:
            ok, value = self._validated(editing, (text or payload or "").strip())
            if not ok:
                return self._retry(editing)
            value = self.store_value(editing, value)
            state["data"][editing] = value
            state.pop("editing")
            ack = self.acknowledge(editing, value)
            return [_with_ack(ack, self._confirmation_prompt(session))], False

        if state.get("confirming"):
            return self._handle_summary(session, text, payload)

        i = state.get("step", 0)
        field = self.steps[i]
        ok, value = self._validated(field, (text or payload or "").strip())
        if not ok:
            return self._retry(field)

        value = self.store_value(field, value)
        state.setdefault("data", {})[field] = value
        ack = self.acknowledge(field, value)
        i += 1
        while i < len(self.steps) and self.steps[i] in state["data"]:
            i += 1  # already answered (e.g. pre-filled from the first message, C8)
        state["step"] = i
        if i < len(self.steps):
            return [_with_ack(ack, self._prompt(i))], False
        if self.require_confirmation:
            state["confirming"] = True
            return [_with_ack(ack, self._confirmation_prompt(session))], False
        finished = self.finish(session)
        finished[0] = _with_ack(ack, finished[0])
        return finished, True

    def finish(self, session):
        raise NotImplementedError

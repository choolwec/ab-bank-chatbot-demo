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


class FormFlow:
    name = "form"
    # list of (field_key, prompt_text)
    steps: list[tuple[str, str]] = []
    # optional {field_key: (is_valid_fn, retry_message)} — checked before a
    # step's answer is stored; on failure the same step re-prompts with the
    # retry message instead of advancing.
    validators: dict[str, tuple] = {}

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

    def resume(self, session):
        """Re-issue the current step's prompt without touching collected data.

        Used when a returning page load reopens an in-progress flow — a
        half-finished fraud report must never be silently discarded.
        """
        i = min(session.flow_state.get("step", 0), len(self.steps) - 1)
        return [self._prompt(i)]

    def handle(self, session, text, payload=None):
        state = session.flow_state
        i = state.get("step", 0)
        field = self.steps[i][0]
        value = (text or payload or "").strip()

        validator = self.validators.get(field)
        if validator:
            is_valid, retry_text = validator
            if not is_valid(value):
                return [{"text": retry_text, "buttons": [CANCEL_BUTTON]}], False

        state.setdefault("data", {})[field] = value
        i += 1
        state["step"] = i
        if i < len(self.steps):
            return [self._prompt(i)], False
        return self.finish(session), True

    def finish(self, session):
        raise NotImplementedError

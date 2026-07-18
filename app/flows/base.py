"""Shared flow machinery: a simple step-form state machine.

A flow returns (replies, done). Replies are dicts: {"text": str, "buttons":
[{"label","payload"}]}. The router guarantees the last reply always carries
at least one button (no dead ends, §1 rule 1).
"""

CANCEL_BUTTON = {"label": "Back to menu", "payload": "cancel_flow"}
MENU_BUTTON = {"label": "Main menu", "payload": "menu"}
HUMAN_BUTTON = {"label": "Talk to a person", "payload": "human_handoff"}


class FormFlow:
    name = "form"
    # list of (field_key, prompt_text)
    steps: list[tuple[str, str]] = []

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

    def handle(self, session, text, payload=None):
        state = session.flow_state
        i = state.get("step", 0)
        state.setdefault("data", {})[self.steps[i][0]] = (text or payload or "").strip()
        i += 1
        state["step"] = i
        if i < len(self.steps):
            return [self._prompt(i)], False
        return self.finish(session), True

    def finish(self, session):
        raise NotImplementedError

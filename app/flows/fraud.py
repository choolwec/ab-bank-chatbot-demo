"""Fraud / scam / lost-card priority flow (§3.1C).

Fires on intent OR the urgent keyword scan, from any point in a conversation.
Creates an urgent ticket with the transcript attached. The bot NEVER marks
these resolved — a person closes the case.

No "Shall I send it?" step (C7): speed matters more here than polish, so the
finish message shows what was sent instead.
"""

from .. import audit
from ..messages import msg
from .base import (
    HUMAN_BUTTON,
    MENU_BUTTON,
    SKIPPED,
    FormFlow,
    is_valid_contact,
    read_back,
    store_contact,
)


class FraudFlow(FormFlow):
    name = "fraud"
    steps = ["what_happened", "when", "channel", "contact"]
    validators = {"contact": is_valid_contact}

    def message_keys(self):
        return super().message_keys() + [
            "fraud.intro.lost_card", "fraud.intro.fraud", "fraud.finish",
            "fraud.contact_skipped", "read_back",
        ]

    def intro(self, session, kind):
        key = "fraud.intro.lost_card" if kind == "lost_card" else "fraud.intro.fraud"
        return [{"text": msg(key), "buttons": []}]

    def store_value(self, field, value):
        return store_contact(value) if field == "contact" else value

    def acknowledge(self, field, value):
        if field != "contact":
            return None
        if value == SKIPPED:
            return msg("fraud.contact_skipped")
        return msg("read_back", value=read_back(value))

    def finish(self, session):
        data = dict(session.flow_state.get("data", {}))
        data["kind"] = session.flow_state.get("kind") or "fraud"
        summary = self.summary(session)
        ref = audit.create_ticket("fraud", data, session.transcript)
        return [
            {
                "text": msg("fraud.finish", ref=ref, summary=summary),
                "buttons": [HUMAN_BUTTON, MENU_BUTTON],
            }
        ]

"""Fraud / scam / lost-card priority flow (§3.1C).

Fires on intent OR the urgent keyword scan, from any point in a conversation.
Creates an urgent ticket with the transcript attached. The bot NEVER marks
these resolved — a person closes the case.
"""

from .. import audit
from ..messages import msg
from .base import (
    HUMAN_BUTTON,
    MENU_BUTTON,
    FormFlow,
    clean_phone,
    format_phone,
    is_skip,
    is_valid_email,
    is_valid_zambian_phone,
)

SKIPPED = "skipped"


def _valid_contact(text):
    return is_valid_zambian_phone(text) or is_valid_email(text) or is_skip(text)


class FraudFlow(FormFlow):
    name = "fraud"
    require_confirmation = True
    interruptible_fields = frozenset({"what_happened"})
    steps = ["what_happened", "when", "channel", "contact"]
    validators = {"contact": _valid_contact}

    def message_keys(self):
        return super().message_keys() + [
            "fraud.intro.lost_card", "fraud.intro.fraud", "fraud.finish",
            "fraud.contact_skipped", "read_back",
        ]

    def intro(self, session, kind):
        key = "fraud.intro.lost_card" if kind == "lost_card" else "fraud.intro.fraud"
        return [{"text": msg(key), "buttons": []}]

    def store_value(self, field, value):
        if field != "contact":
            return value
        if is_skip(value):
            return SKIPPED
        return clean_phone(value) if is_valid_zambian_phone(value) else value.strip()

    def acknowledge(self, field, value):
        if field != "contact":
            return None
        if value == SKIPPED:
            return msg("fraud.contact_skipped")
        if is_valid_zambian_phone(value):
            return msg("read_back", value=format_phone(value))
        return msg("read_back", value=value)

    def finish(self, session):
        data = dict(session.flow_state.get("data", {}))
        data["kind"] = session.flow_state.get("kind") or "fraud"
        ref = audit.create_ticket("fraud", data, session.transcript)
        return [{"text": msg("fraud.finish", ref=ref), "buttons": [HUMAN_BUTTON, MENU_BUTTON]}]

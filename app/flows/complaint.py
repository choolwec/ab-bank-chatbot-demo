"""Complaint intake flow (§3.1C): structured intake feeding the bank's
BoZ-mandated complaints unit, with a reference number returned (§7)."""

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


class ComplaintFlow(FormFlow):
    name = "complaint"
    require_confirmation = True
    steps = ["topic", "details", "contact"]
    # A phone number, an email, or "skip" -- validated so a typo'd number
    # can be corrected at the summary ("sorry, it's 0966 ...", C6).
    validators = {"contact": is_valid_contact}

    def message_keys(self):
        return super().message_keys() + ["complaint.finish", "read_back"]

    def store_value(self, field, value):
        return store_contact(value) if field == "contact" else value

    def acknowledge(self, field, value, session=None):
        if field == "contact" and value != SKIPPED:
            return msg("read_back", value=read_back(value))
        return None

    def finish(self, session):
        data = dict(session.flow_state.get("data", {}))
        ref = audit.create_ticket("complaint", data, session.transcript)
        return [{"text": msg("complaint.finish", ref=ref), "buttons": [HUMAN_BUTTON, MENU_BUTTON]}]

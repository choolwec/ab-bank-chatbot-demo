"""Complaint intake flow (§3.1C): structured intake feeding the bank's
BoZ-mandated complaints unit, with a reference number returned (§7)."""

from .. import audit
from ..messages import msg
from .base import HUMAN_BUTTON, MENU_BUTTON, FormFlow


class ComplaintFlow(FormFlow):
    name = "complaint"
    require_confirmation = True
    interruptible_fields = frozenset({"details"})
    steps = ["topic", "details", "contact"]

    def message_keys(self):
        return super().message_keys() + ["complaint.finish"]

    def finish(self, session):
        data = dict(session.flow_state.get("data", {}))
        ref = audit.create_ticket("complaint", data, session.transcript)
        return [{"text": msg("complaint.finish", ref=ref), "buttons": [HUMAN_BUTTON, MENU_BUTTON]}]

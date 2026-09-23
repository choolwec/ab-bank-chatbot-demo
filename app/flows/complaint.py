"""Complaint intake flow (§3.1C): structured intake feeding the bank's
BoZ-mandated complaints unit, with a reference number returned (§7)."""

from .. import audit
from .base import HUMAN_BUTTON, MENU_BUTTON, FormFlow


class ComplaintFlow(FormFlow):
    name = "complaint"
    topic_label = "complaint"
    require_confirmation = True
    interruptible_fields = frozenset({"details"})
    steps = [
        (
            "topic",
            "I'm sorry you've had a poor experience — I'll log a formal complaint "
            "for you.\nFirst: what is your complaint about? (For example: an "
            "account, eTumba, a loan, service at a branch.)",
        ),
        ("details", "Thank you. Please describe what happened."),
        (
            "contact",
            "What's the best phone number or email for updates on this complaint? "
            "(Type 'skip' if you'd rather not — it is logged either way.)",
        ),
    ]

    def finish(self, session):
        data = dict(session.flow_state.get("data", {}))
        ref = audit.create_ticket("complaint", data, session.transcript)
        text = (
            f"Your complaint has been logged with reference {ref} and goes "
            "straight to our complaints team, who handle it under the Bank of "
            "Zambia's complaints-handling requirements. "
            "[CONFIRM: response-time commitment to quote here.]\n"
            "Please keep your reference number — any member of staff can look it up."
        )
        return [{"text": text, "buttons": [HUMAN_BUTTON, MENU_BUTTON]}]

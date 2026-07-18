"""Callback capture ("talk to a person", §3.1A): name, phone, topic, time.

Routed to staff with a realistic response-time promise — within one working
day. The transcript rides along so the customer never repeats themselves.
"""

from .. import audit
from .base import CANCEL_BUTTON, MENU_BUTTON, FormFlow


class LeadFlow(FormFlow):
    name = "lead"
    steps = [
        (
            "name",
            "Of course — I'll arrange for our team to call you back.\n"
            "What's your name?",
        ),
        ("phone", "Thanks. What phone number should we call?"),
        ("topic", "And what would you like to discuss?"),
        ("time", "When is best to call — morning or afternoon?"),
    ]

    def _prompt(self, i):
        prompt = super()._prompt(i)
        if self.steps[i][0] == "time":
            prompt["buttons"] = [
                {"label": "Morning", "payload": "Morning"},
                {"label": "Afternoon", "payload": "Afternoon"},
                CANCEL_BUTTON,
            ]
        return prompt

    def finish(self, session):
        data = dict(session.flow_state.get("data", {}))
        ref = audit.create_ticket("callback", data, session.transcript)
        text = (
            "Done — that's everything I need. Our team will call you within one "
            f"working day. Your reference is {ref}.\n"
            "Is there anything else I can help with in the meantime?"
        )
        return [{"text": text, "buttons": [MENU_BUTTON]}]

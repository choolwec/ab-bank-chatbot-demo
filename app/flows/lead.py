"""Callback capture ("talk to a person", §3.1A): name, phone, topic, time.

Routed to staff with a realistic response-time promise — within one working
day. The transcript rides along so the customer never repeats themselves.
"""

from .. import audit
from ..messages import msg
from .base import (
    CANCEL_BUTTON,
    DONE_BUTTON,
    MENU_BUTTON,
    FormFlow,
    clean_phone,
    is_valid_zambian_phone,
)


class LeadFlow(FormFlow):
    name = "lead"
    require_confirmation = True
    steps = ["name", "phone", "topic", "time"]
    validators = {"phone": is_valid_zambian_phone}

    def message_keys(self):
        return super().message_keys() + ["lead.finish"]

    def store_value(self, field, value):
        # One canonical form for the contact centre: "0977123456".
        return clean_phone(value) if field == "phone" else value

    def _prompt(self, i):
        prompt = super()._prompt(i)
        if self.steps[i] == "time":
            prompt["buttons"] = [
                {"label": "Morning", "payload": "Morning"},
                {"label": "Afternoon", "payload": "Afternoon"},
                CANCEL_BUTTON,
            ]
        return prompt

    def finish(self, session):
        data = dict(session.flow_state.get("data", {}))
        ref = audit.create_ticket("callback", data, session.transcript)
        return [
            {
                "text": msg("lead.finish", ref=ref),
                "buttons": [DONE_BUTTON, MENU_BUTTON],
                # "Is there anything else?" -- typed yes/no answer it (C3).
                "yes": "menu",
                "no": "thanks_goodbye",
            }
        ]

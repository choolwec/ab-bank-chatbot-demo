"""Callback capture ("talk to a person", §3.1A): name, phone, topic, time.

Routed to staff with a realistic response-time promise — within one working
day. The transcript rides along so the customer never repeats themselves.
"""

from .. import audit
from ..messages import button, msg
from .base import (
    CANCEL_BUTTON,
    DONE_BUTTON,
    MENU_BUTTON,
    FormFlow,
    clean_phone,
    is_valid_zambian_phone,
    read_back,
)


class LeadFlow(FormFlow):
    name = "lead"
    require_confirmation = True
    steps = ["name", "phone", "topic", "time"]
    validators = {"phone": is_valid_zambian_phone}

    def message_keys(self):
        return super().message_keys() + ["lead.finish", "read_back"]

    def store_value(self, field, value):
        # One canonical form for the contact centre: "0977123456".
        return clean_phone(value) if field == "phone" else value

    def acknowledge(self, field, value, session=None):
        if field == "phone":
            return msg("read_back", value=read_back(value))
        if field == "name" and session is not None and not session.slots.get("name_used"):
            first = value.split()[0] if value.split() else ""
            # Only something that looks like a name: "Thanks, Mary." (C11)
            if first.isalpha() and 1 < len(first) <= 20:
                session.slots["name_used"] = True
                return msg("thanks_name", name=first.capitalize())
        return None

    def _prompt(self, i, session=None):
        prompt = super()._prompt(i, session)
        if self.steps[i] == "time":
            prompt["buttons"] = [
                button("morning", "time:Morning"),
                button("afternoon", "time:Afternoon"),
                CANCEL_BUTTON,
            ]
        return prompt

    def finish(self, session):
        data = dict(session.flow_state.get("data", {}))
        ref = self.create_ticket(session, "callback", data)
        return [
            {
                "text": msg("lead.finish", ref=ref),
                "buttons": [DONE_BUTTON, MENU_BUTTON],
                # "Is there anything else?" -- typed yes/no answer it (C3).
                "yes": "menu",
                "no": "thanks_goodbye",
            }
        ]

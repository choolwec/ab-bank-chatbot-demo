"""Callback capture ("talk to a person", §3.1A): name, phone, topic, time.

Routed to staff with a realistic response-time promise — within one working
day. The transcript rides along so the customer never repeats themselves.

MK2: one optional last question before the summary -- may AB Bank send news
and offers? The answer ("yes"/"no") and when it was given go on the ticket,
and "yes" adds the Jira label marketing-consent. It is skipped when
MARKETING_CONSENT_ENABLED is off or the customer opted out this session
("unsubscribe", router._opt_out). MK3: the ticket carries the campaign source.
"""

import datetime as dt

from .. import audit, campaign, config, guards
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


CONSENT = "marketing_consent"
CONSENT_AT = "marketing_consent_at"
NOT_ASKED = "not_asked"
OPT_OUT_SLOT = "marketing_opt_out"
# Consent needs a clear answer: anything else re-asks with the buttons.
_CONSENT_YES = frozenset({"i agree", "agree", "i consent", "yes i agree", "yes send them"})
_CONSENT_NO = frozenset({"i don't agree", "i dont agree", "dont", "don't", "no offers"})


def consent_answer(text):
    """True / False for a clear yes or no to the consent question, else None."""
    t = guards.normalise(text)
    if t in _CONSENT_YES:
        return True
    if t in _CONSENT_NO:
        return False
    return guards.yes_no(text)


def _now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def record_opt_out(session):
    """Opted out (router._opt_out): never asked again this session, and a
    callback already in progress records "no" instead of any earlier "yes"."""
    session.slots[OPT_OUT_SLOT] = _now_iso()
    if session.active_flow == "lead":
        data = session.flow_state.setdefault("data", {})
        if data.get(CONSENT) != "no":
            data[CONSENT] = "no"
            data[CONSENT_AT] = session.slots[OPT_OUT_SLOT]


class LeadFlow(FormFlow):
    name = "lead"
    require_confirmation = True
    steps = ["name", "phone", "topic", "time", CONSENT]
    validators = {
        "phone": is_valid_zambian_phone,
        CONSENT: lambda text: consent_answer(text) is not None,
    }

    @property
    def correctable(self):
        return frozenset({"phone"})  # consent is changed with its buttons

    def message_keys(self):
        return super().message_keys() + [
            "lead.finish", "lead.finish_out_of_hours", "read_back",
            "lead.summary.marketing_consent_yes", "lead.summary.marketing_consent_no",
        ]

    def skip_step(self, session, field):
        if field != CONSENT:
            return False
        return not config.marketing_consent_enabled() or bool(session.slots.get(OPT_OUT_SLOT))

    def store_value(self, field, value):
        # One canonical form for the contact centre: "0977123456".
        if field == CONSENT:
            return "yes" if consent_answer(value) else "no"
        return clean_phone(value) if field == "phone" else value

    def stored(self, session, field, value):
        if field == CONSENT:
            session.flow_state["data"][CONSENT_AT] = _now_iso()

    def display_value(self, field, value):
        if field == CONSENT:
            return msg(f"lead.summary.marketing_consent_{value}")
        return super().display_value(field, value)

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
        elif self.steps[i] == CONSENT:
            yes, no = CONSENT + ":yes", CONSENT + ":no"
            prompt["buttons"] = [button("yes_send_offers", yes), button("no_thanks", no), CANCEL_BUTTON]
            prompt["yes"], prompt["no"] = yes, no  # a typed yes/no answers it (C3)
        return prompt

    def _retry(self, field):
        if field != CONSENT:
            return super()._retry(field)
        # The retry says "tap Yes or No", so it must carry those buttons.
        prompt = self._prompt(self.steps.index(CONSENT))
        return [dict(prompt, text=msg(f"{self.name}.retry.{CONSENT}"))], False

    def finish(self, session):
        data = dict(session.flow_state.get("data", {}))
        if CONSENT not in data:
            # Never asked: opted out earlier this session, or the flag is off.
            if session.slots.get(OPT_OUT_SLOT):
                data[CONSENT], data[CONSENT_AT] = "no", session.slots[OPT_OUT_SLOT]
            else:
                data[CONSENT] = NOT_ASKED
        data["source"] = campaign.source_of(session)
        ref = self.create_ticket(session, "callback", data)
        from .. import hours

        key = "lead.finish" if hours.is_open() else "lead.finish_out_of_hours"
        return [
            {
                "text": msg(key, ref=ref, when=hours.when_phrase()),
                "buttons": [DONE_BUTTON, MENU_BUTTON],
                # "Is there anything else?" -- typed yes/no answer it (C3).
                "yes": "menu",
                "no": "thanks_goodbye",
                # H5: a resolved conversation; the router may ask for feedback.
                "resolved": "callback",
            }
        ]

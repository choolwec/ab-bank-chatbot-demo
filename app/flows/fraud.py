"""Fraud / scam / lost-card priority flow (§3.1C).

Fires on intent OR the urgent keyword scan, from any point in a conversation.
Creates an urgent ticket with the transcript attached. The bot NEVER marks
these resolved — a person closes the case.
"""

from .. import audit, config
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

CONTACT_RETRY_TEXT = (
    "That doesn't look like a valid number — please send it as 09XXXXXXX "
    "(10 digits), 260XXXXXXXXX (12 digits), or +260XXXXXXXXX, or an email "
    "address, so our fraud team can actually reach you. You can also type "
    "'skip'."
)
CONTACT_SKIPPED_TEXT = (
    "Without a number we can't call you back. Please call {contact_phone} so "
    "our team can help you."
)
SKIPPED = "skipped"


def _valid_contact(text):
    return is_valid_zambian_phone(text) or is_valid_email(text) or is_skip(text)


class FraudFlow(FormFlow):
    name = "fraud"
    topic_label = "fraud report"
    require_confirmation = True
    interruptible_fields = frozenset({"what_happened"})
    steps = [
        ("what_happened", "Please tell me briefly what happened."),
        ("when", "When did this happen? (For example: today, yesterday, or a date.)"),
        (
            "channel",
            "Which service was involved — card or ATM, eTumba, internet banking, "
            "or a branch?",
        ),
        (
            "contact",
            "What's the best phone number to reach you on right now, so our "
            "fraud team can follow up immediately? (An email address works "
            "too.)",
        ),
    ]
    validators = {"contact": (_valid_contact, CONTACT_RETRY_TEXT)}

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
            return CONTACT_SKIPPED_TEXT
        if is_valid_zambian_phone(value):
            return f"Got it: {format_phone(value)}."
        return f"Got it: {value}."

    def intro(self, session, kind):
        emergency = config.CONTACTS["emergency_phone"]
        if kind == "lost_card":
            text = (
                "I'm sorry to hear that — let's secure your card straight away.\n"
                f"Call us now on {emergency} to block your card immediately.\n"
                "I'll also take a few details so our team can follow up with you."
            )
        else:
            text = (
                "I'm sorry this has happened. You've done the right thing by "
                "reporting it, and I'm treating it as urgent.\n"
                f"If money is at risk right now, call us immediately on {emergency}.\n"
                "I'll take a few details for our fraud team, and a person will "
                "follow up with you."
            )
        return [{"text": text, "buttons": []}]

    def finish(self, session):
        data = dict(session.flow_state.get("data", {}))
        data["kind"] = session.flow_state.get("kind") or "fraud"
        ref = audit.create_ticket("fraud", data, session.transcript)
        emergency = config.CONTACTS["emergency_phone"]
        text = (
            f"Thank you. I've raised an urgent case for our team — your reference "
            f"is {ref}. A member of staff will contact you as a priority.\n"
            "This case stays open until a person from the bank has resolved it "
            "with you — I won't close it myself.\n"
            f"For immediate help at any time, call {emergency}."
        )
        return [{"text": text, "buttons": [HUMAN_BUTTON, MENU_BUTTON]}]

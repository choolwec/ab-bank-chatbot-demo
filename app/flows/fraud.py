"""Fraud / scam / lost-card priority flow (§3.1C).

Fires on intent OR the urgent keyword scan, from any point in a conversation.
Creates an urgent ticket with the transcript attached. The bot NEVER marks
these resolved — a person closes the case.

No "Shall I send it?" step (C7): speed matters more here than polish, so the
finish message shows what was sent instead.

Pre-fill (C8): when the message that started the report already describes
it ("I lost my card yesterday at cairo branch"), that message becomes
`what_happened`, and when/channel found in it are confirmed with ONE yes/no
question instead of asked one by one. "No, let me explain" falls back to the
normal questions.
"""

from .. import audit
from ..extract import CHANNEL_PHRASE, extract
from ..messages import button, msg
from .base import (
    CANCEL_BUTTON,
    HUMAN_BUTTON,
    MENU_BUTTON,
    SKIPPED,
    FormFlow,
    is_valid_contact,
    read_back,
    store_contact,
)

PREFILL_YES = "prefill_yes"
PREFILL_NO = "prefill_no"
# A trigger is used as the description when it has at least this many words
# AND states a fact (when / what service / an amount) -- "i think i was
# scammed" is five words but describes nothing, so it still gets asked.
PREFILL_MIN_WORDS = 5
# ... or when it is long enough to be a description on its own.
PREFILL_DESCRIPTION_WORDS = 10
HINT_FIELDS = ("when_hint", "branch_hint", "amount_hint")


class FraudFlow(FormFlow):
    name = "fraud"
    steps = ["what_happened", "when", "channel", "contact"]
    validators = {"contact": is_valid_contact}

    def message_keys(self):
        return super().message_keys() + [
            "fraud.intro.lost_card", "fraud.intro.fraud", "fraud.finish",
            "fraud.contact_skipped", "read_back",
            "fraud.prefill.both", "fraud.prefill.when", "fraud.prefill.channel",
        ]

    def intro(self, session, kind):
        key = "fraud.intro.lost_card" if kind == "lost_card" else "fraud.intro.fraud"
        return [{"text": msg(key), "buttons": []}]

    # --- C8 pre-fill -------------------------------------------------------

    def start(self, session, kind=None, trigger=None):
        replies, done = super().start(session, kind)
        words = (trigger or "").split()
        if len(words) < PREFILL_MIN_WORDS:
            return replies, done
        facts = extract(trigger)
        if not facts and len(words) < PREFILL_DESCRIPTION_WORDS:
            return replies, done
        state = session.flow_state
        state["data"]["what_happened"] = trigger.strip()
        for key in HINT_FIELDS:
            if facts.get(key):
                state["data"][key] = facts[key]
        prefill = {k: facts[k] for k in ("when", "channel") if facts.get(k)}
        intro = self.intro(session, kind)
        if prefill:
            # Stored at once (tentatively) so a summary or digression shown
            # while confirming is accurate; "No" removes them again.
            state["data"].update(prefill)
            state["prefill"] = prefill
            return self.opening(session, intro, self._prefill_prompt(prefill)), done
        state["step"] = self._next_step(state)
        return self.opening(session, intro, self._prompt(state["step"])), done

    def _prefill_prompt(self, prefill):
        when, channel = prefill.get("when"), prefill.get("channel")
        if when and channel:
            text = msg("fraud.prefill.both", when=when, channel=CHANNEL_PHRASE[channel])
        elif when:
            text = msg("fraud.prefill.when", when=when)
        else:
            text = msg("fraud.prefill.channel", channel=CHANNEL_PHRASE[channel])
        return {
            "text": text,
            "buttons": [
                button("yes_that_s_right", PREFILL_YES),
                button("no_let_me_explain", PREFILL_NO),
                CANCEL_BUTTON,
            ],
            "yes": PREFILL_YES,
            "no": PREFILL_NO,
        }

    def _next_step(self, state):
        data = state["data"]
        return next((i for i, f in enumerate(self.steps) if f not in data), len(self.steps))

    def resume(self, session):
        prefill = session.flow_state.get("prefill")
        if prefill:
            return [self._prefill_prompt(prefill)]
        return super().resume(session)

    def handle(self, session, text, payload=None):
        state = session.flow_state
        prefill = state.get("prefill")
        if not prefill:
            return super().handle(session, text, payload)
        if payload == PREFILL_YES:
            state.pop("prefill")
            state["step"] = self._next_step(state)
            return [self._prompt(state["step"])], False
        if payload == PREFILL_NO:
            # Start over with the normal questions; the trigger stays in the
            # transcript that rides along with the ticket.
            state.pop("prefill")
            state["data"] = {}
            state["step"] = 0
            return [self._prompt(0)], False
        return [self._prefill_prompt(prefill)], False

    # --- contact read-back --------------------------------------------------

    def store_value(self, field, value):
        return store_contact(value) if field == "contact" else value

    def acknowledge(self, field, value, session=None):
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

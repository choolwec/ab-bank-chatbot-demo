"""WhatsApp coexistence pause (ticket W11, decision D5 option B).

Staff keep the WhatsApp Business app on the official number and the bot runs
on the Cloud API beside them (docs/multi-platform-research.md §5.1, §7.6).
When a person replies from the app, Meta sends an smb_message_echoes event;
whatsapp.parse() turns it into an InboundMessage with kind "echo", which goes
through the durable inbox and the worker like any other event. Here:

  echo      pause the bot for that customer for COEXISTENCE_PAUSE_HOURS from
            the staff reply, using the same pause as the desk and Messenger
            (session.bot_paused_until, messaging.py step 4). Each new echo
            restarts the timer. Logged as action=human_reply_echo: no text,
            no raw id (Session.id is random, user_hash is an HMAC).
  resume    after COEXISTENCE_PAUSE_HOURS with no new echo, or when the
            customer taps or types "menu" (router.COMMANDS). Logged as
            action=coexistence_resumed.
  urgent    while paused, a HARD fraud / lost-card signal (guards.urgent_scan)
            still creates a fraud ticket (and so a Jira issue), once per
            pause, plus ONE short safety reply with the emergency number
            (coexistence.urgent_safety). Staff may not be looking at the app,
            and a card block cannot wait for them.
  unfinished a fraud report or complaint in progress when staff reply is not
            dropped: its data goes on a ticket at once, as a handoff does.

With COEXISTENCE_ENABLED off (the default until the number decision is
confirmed) an echo is logged as action=human_reply_echo_ignored and nothing
else changes; a pause already running is lifted on the customer's next
message.
"""

import time

from .. import audit, config, guards
from ..desk.bridge import CONVERSATION_SLOT
from ..messages import button, msg
from . import messenger

PAUSED_SLOT = "coexistence_paused_at"   # when the latest staff reply was sent
URGENT_SLOT = "coexistence_urgent_ref"  # the ticket raised during this pause
REPORTED_WHILE = "staff_replying_in_business_app"


def _log(session, text, action):
    audit.log_event(session.id, "system", text, action=action, channel=session.channel,
                    user_hash=session.user_hash)


def active(session) -> bool:
    return bool(session.slots.get(PAUSED_SLOT))


# --- the echo ---------------------------------------------------------------------

def handle_echo(session, message, now: float | None = None) -> dict:
    """A person replied to this customer from the Business app."""
    now = now or time.time()
    if not config.coexistence_enabled():
        _log(session, "staff reply from the WhatsApp Business app: ignored (coexistence off)",
             "human_reply_echo_ignored")
        return {"action": "human_reply_echo_ignored"}
    sent_at = min(message.ts or now, now)
    until = sent_at + config.coexistence_pause_hours() * 3600
    if until <= now:  # a late redelivery: that pause would already be over
        _log(session, "late staff reply echo: pause already over", "human_reply_echo_stale")
        return {"action": "human_reply_echo_stale"}
    _keep_unfinished_report(session)
    session.slots[PAUSED_SLOT] = max(session.slots.get(PAUSED_SLOT) or 0, sent_at)
    # The same pause the desk and Messenger use. max() inside: a longer desk
    # pause is never shortened; a newer echo always runs to its own end.
    messenger.pause(session, (until - time.time()) / 3600)
    _log(session, "staff replied from the WhatsApp Business app: bot paused", "human_reply_echo")
    return {"action": "human_reply_echo"}


def _keep_unfinished_report(session) -> None:
    """A fraud report or complaint in progress goes on its ticket now, so a
    staff reply mid-report can never lose it (compare router._handoff_to_inbox)."""
    from ..flows import FLOWS

    flow = session.active_flow
    data = dict(session.flow_state.get("data") or {})
    if flow not in ("fraud", "complaint") or not data:
        return
    if flow == "fraud":
        data["kind"] = session.flow_state.get("kind") or "fraud"
    data["unfinished"] = "yes"
    data["reported_while"] = REPORTED_WHILE
    ref = FLOWS[flow].create_ticket(session, flow, data)
    session.active_flow = None
    session.flow_state = {}
    _log(session, f"unfinished {flow} report kept on {ref}: staff took over", "coexistence_unfinished_ticket")


# --- resuming ---------------------------------------------------------------------

def _resume(session, reason: str) -> None:
    session.slots.pop(PAUSED_SLOT, None)
    session.slots.pop(URGENT_SLOT, None)
    if not session.slots.get(CONVERSATION_SLOT):  # an agent-desk pause runs its own course
        messenger.resume_bot(session)
    _log(session, f"coexistence pause ended ({reason}): bot resumed", "coexistence_resumed")


def expire(session, now: float) -> bool:
    """Lift the pause after COEXISTENCE_PAUSE_HOURS with no new echo, or at
    once when the flag has been turned off. True if it resumed."""
    if not active(session):
        return False
    if not config.coexistence_enabled():
        _resume(session, "coexistence switched off")
        return True
    if session.bot_paused_until <= now:
        _resume(session, "timeout")
        return True
    return False


def is_menu(message) -> bool:
    if message.payload == "menu":
        return True
    if message.text:
        from ..router import COMMANDS

        return COMMANDS.get(guards.normalise(message.text)) == "menu"
    return False


def resume_on_menu(session, message) -> bool:
    """The customer asked for the bot back. True if it resumed."""
    if not active(session) or not is_menu(message) or session.slots.get(CONVERSATION_SLOT):
        return False
    _resume(session, "customer asked for the menu")
    return True


# --- urgent while paused ------------------------------------------------------------

def urgent_while_paused(session, message) -> list[dict]:
    """A hard fraud / lost-card message while staff have the conversation:
    ticket it (once per pause) and send one safety reply. Returns the replies
    (empty when nothing is sent). The text is already masked (inbox.py)."""
    if not active(session) or not message.text:
        return []
    signal = guards.urgent_scan(message.text)
    if not signal or signal.kind != "fraud" or not signal.is_hard:
        return []
    ref = session.slots.get(URGENT_SLOT)
    if ref:
        _log(session, f"urgent message while staff are replying: already on {ref}", "coexistence_urgent_repeat")
        return []
    from ..flows import FLOWS

    data = {"kind": signal.sub or "fraud", "what_happened": message.text, "reported_while": REPORTED_WHILE}
    ref = FLOWS["fraud"].create_ticket(session, "fraud", data)
    session.slots[URGENT_SLOT] = ref
    _log(session, f"urgent message while staff are replying: {ref} raised", "coexistence_urgent")
    return [{"text": msg("coexistence.urgent_safety", ref=ref), "buttons": [button("main_menu", "menu")]}]

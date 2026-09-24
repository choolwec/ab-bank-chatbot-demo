"""Between our channels and the agent desk (ticket H2).

Handoff (WhatsApp): router._handoff_to_inbox has already created the handoff
ticket (and so the Jira issue). WhatsAppSender.pass_to_desk() then calls
open_conversation(), which
  1. finds or creates the Chatwoot contact: identifier = the session's
     user_hash, plus a name only if the customer gave one;
  2. opens a conversation in the API-channel inbox, status open, with the
     ticket ref and Jira key as custom attributes;
  3. posts the masked transcript as a PRIVATE note;
  4. pauses the bot and stores chatwoot_conversation_id on the session.
If Chatwoot fails, the bot is NOT paused, so the customer is never left
talking to nobody: the ticket is already in Jira and staff follow up from
/admin/cases. Every failure is an audit event (action desk_*) for alerting.

While paused (messaging.py step 4), each customer message is logged as before
and also forwarded to the conversation as an incoming message.

POST /webhooks/chatwoot/{secret}: Chatwoot's webhooks carry no signature
[VERIFY for the installed version], so a long secret sits in the path and is
compared in constant time. 404 while the desk is unconfigured (the route
doesn't exist, as before H2); 403 for a wrong secret.
  message_created, outgoing, not private -> the channel adapter's
      send_free_form(). Outside the 24-h window nothing is sent and a private
      note tells the agent to use the case_update template.
  conversation_status_changed to resolved -> resume_bot()
With no agent reply for DESK_IDLE_HOURS, the next customer message resumes
the bot and a private note tells the desk. Jira stays the system of record.

Everything posted to Chatwoot goes through desk_text(): guards.mask() again,
then phone numbers are redacted as well, so the customer's WhatsApp number
can't reach the desk in any format. Agents reply inside the conversation and
never need it; Jira keeps the contact fields of callbacks and reports.
"""

import datetime as dt
import hmac
import json
import logging
import re

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from .. import audit, config, guards
from ..identity import unseal
from ..messages import msg
from . import chatwoot
from .links import links

log = logging.getLogger("abz.desk")
api = APIRouter()

CONVERSATION_SLOT = "chatwoot_conversation_id"
TRANSCRIPT_TURNS = 40  # the same window as the Jira description
PHONE_MASK = "[PHONE REDACTED]"
# 9-15 digits, single spaces or dashes allowed between them. Not preceded by a
# letter, digit or dash, so a reference like FRD-20260924-1234 is left alone.
PHONE_RE = re.compile(r"(?<![\w\-+])\+?\d(?:[ \-]?\d){8,14}(?!\d)")


def desk_text(text: str) -> str:
    """Text bound for Chatwoot: masked by guards (again), phone numbers too."""
    masked, _ = guards.mask(guards.clean(text or ""))
    return PHONE_RE.sub(PHONE_MASK, masked)


def _log(session, text, action):
    audit.log_event(session.id, "system", text, action=action, channel=session.channel,
                    user_hash=session.user_hash)


def pause(session) -> None:
    """Quiet while a person helps; each agent reply extends it."""
    from ..channels.messenger import pause as _pause

    _pause(session, config.DESK_IDLE_HOURS)


def resume_bot(session) -> None:
    from ..channels.messenger import resume_bot as _resume

    _resume(session)
    session.slots.pop(CONVERSATION_SLOT, None)


# --- handoff ---------------------------------------------------------------------

def _lusaka(iso: str | None) -> str:
    """window_open_until (UTC ISO) -> "25/09/2026 10:00" in Lusaka time."""
    from ..hours import LUSAKA

    if not iso:
        return "?"
    return dt.datetime.fromisoformat(iso).astimezone(LUSAKA).strftime("%d/%m/%Y %H:%M")


def _customer_name(fields: dict) -> str | None:
    """A name the customer gave in a flow, if any (never the platform profile)."""
    candidates = [fields.get("name")] + [v.get("name") for v in fields.values() if isinstance(v, dict)]
    for name in candidates:
        if isinstance(name, str) and name.strip() and desk_text(name) == name:
            return name.strip()[:80]
    return None


def handoff_note(session, ref, jira_key) -> str:
    from ..flows.base import reply_to

    header = msg("desk.note.handoff", ref=ref or "?", jira=jira_key or msg("desk.jira_pending"),
                 channel=session.channel, until=_lusaka(reply_to(session).get("window_open_until")))
    lines = [f"[{t['role']}] {desk_text(t['text'])}" for t in session.transcript[-TRANSCRIPT_TURNS:]]
    return header + "\n\n" + "\n".join(lines)


def open_conversation(session, session_key: str, ref: str | None) -> bool:
    """Put this conversation on the desk and pause the bot. True on success."""
    if not config.chatwoot_configured():
        _log(session, "desk not configured: the handoff stays with its ticket", "desk_failed")
        return False
    ticket = audit.get_ticket(ref) if ref else None
    jira_key = (ticket or {}).get("jira_key")
    attributes = {"ticket_ref": ref or "", "jira_key": jira_key or "", "channel": session.channel}
    client = chatwoot.client
    try:
        contact_id = client.ensure_contact(session.user_hash, _customer_name((ticket or {}).get("fields", {})))
        conv = client.create_conversation(contact_id, session.user_hash, attributes)
    except chatwoot.ChatwootError as exc:
        _log(session, f"desk handoff failed ({exc}): the handoff stays with its ticket", "desk_failed")
        return False
    links.save(conv, session_key, session.channel, ref)
    session.slots[CONVERSATION_SLOT] = conv
    pause(session)
    _log(session, f"desk conversation {conv} opened for {ref}", "desk_handoff")
    try:
        client.private_note(conv, handoff_note(session, ref, jira_key))
    except chatwoot.ChatwootError as exc:  # agents still have the Jira ticket
        _log(session, f"desk transcript note failed ({exc})", "desk_note_failed")
    return True


# --- while paused ------------------------------------------------------------------

def forward(session, text: str) -> None:
    """A customer message that arrived while an agent has the conversation."""
    conv = session.slots.get(CONVERSATION_SLOT)
    if not conv or not config.chatwoot_configured():
        return
    try:
        chatwoot.client.forward_incoming(conv, desk_text(text))
    except chatwoot.ChatwootError as exc:
        _log(session, f"desk forward failed ({exc})", "desk_forward_failed")


def expire_idle(session, now: float) -> bool:
    """The idle fallback: no agent reply for DESK_IDLE_HOURS -> the bot
    answers again, and the desk is told. True if it resumed."""
    conv = session.slots.get(CONVERSATION_SLOT)
    if not conv or session.bot_paused_until > now:
        return False
    resume_bot(session)
    _log(session, f"no agent reply on desk conversation {conv}: bot resumed", "desk_idle_resume")
    if config.chatwoot_configured():
        try:
            chatwoot.client.private_note(conv, msg("desk.note.bot_resumed_idle", hours=config.DESK_IDLE_HOURS))
        except chatwoot.ChatwootError as exc:
            _log(session, f"desk note failed ({exc})", "desk_note_failed")
    return True


# --- the webhook: agent replies and resolution ---------------------------------------

def _note(conv, text: str) -> None:
    try:
        chatwoot.client.private_note(conv, text)
    except chatwoot.ChatwootError:
        log.warning("desk note failed for conversation %s", conv)


def _is_agent_reply(body: dict) -> bool:
    """An agent's reply to the customer: outgoing, public, plain text [VERIFY
    values]. Our own posts are incoming or private, so they never loop."""
    if body.get("message_type") not in ("outgoing", 1):
        return False
    if body.get("private") or (body.get("content_type") or "text") != "text":
        return False
    return (body.get("sender") or {}).get("type") != "contact"


def _open_session(link):
    from .. import session as session_mod

    return session_mod.store.session(link["session_key"], link["channel"])


def agent_reply(body: dict) -> str:
    if not _is_agent_reply(body):
        return "ignored"
    conv = chatwoot.conversation_id(body.get("conversation") or {})
    if not conv:
        return "ignored"
    content = (body.get("content") or "").strip()
    link = links.lookup(conv)
    from ..worker import adapters

    adapter = adapters().get(link["channel"]) if link else None
    if adapter is None:
        _note(conv, msg("desk.note.unlinked"))
        audit.log_event("-", "system", f"agent reply on unlinked desk conversation {conv}",
                        action="desk_unlinked")
        return "unlinked"
    from ..channels.whatsapp import WindowClosed

    with _open_session(link) as (session, created):
        sealed = session.slots.get("reply_ref")
        if created or not sealed:
            _note(conv, msg("desk.note.unlinked"))
            _log(session, f"agent reply on desk conversation {conv}: no reply address", "desk_unlinked")
            return "unlinked"
        if not content:
            _note(conv, msg("desk.note.attachment_not_sent"))
            return "attachment_refused"
        try:
            ok = adapter.send_free_form(unseal(sealed), [{"text": content, "buttons": []}], session)
        except WindowClosed:
            _note(conv, msg("window_closed"))
            _log(session, f"agent reply on desk conversation {conv} refused: 24-h window closed",
                 "desk_window_closed")
            return "window_closed"
        if not ok:
            _note(conv, msg("desk.note.send_failed"))
            _log(session, f"agent reply on desk conversation {conv} failed to send", "desk_send_failed")
            return "send_failed"
        masked, _ = guards.mask(guards.clean(content))
        session.add("agent", masked)
        audit.log_event(session.id, "agent", masked, action="desk_agent_reply", channel=session.channel,
                        user_hash=session.user_hash)
        session.slots[CONVERSATION_SLOT] = conv  # replying takes the conversation (back)
        pause(session)
    if body.get("attachments"):
        _note(conv, msg("desk.note.attachment_not_sent"))
    return "delivered"


def status_changed(body: dict) -> str:
    if body.get("status") != "resolved":
        return "ignored"
    conv = chatwoot.conversation_id(body)
    link = links.lookup(conv) if conv else None
    if not link:
        return "unlinked"
    with _open_session(link) as (session, created):
        if created or str(session.slots.get(CONVERSATION_SLOT)) != str(conv):
            return "ignored"  # an older conversation; a newer one is active
        resume_bot(session)
        _log(session, f"desk conversation {conv} resolved: bot resumed", "desk_resolved")
    return "resumed"


def handle_event(body: dict) -> str:
    """Dispatch one Chatwoot webhook event. Returns what was done."""
    try:
        event = body.get("event")
        if event == "message_created":
            return agent_reply(body)
        if event == "conversation_status_changed":
            return status_changed(body)
        return "ignored"
    except Exception:  # a background task: log, never crash the app
        log.exception("chatwoot event failed")
        return "error"


@api.post("/webhooks/chatwoot/{secret}")
async def webhook(secret: str, request: Request, background: BackgroundTasks):
    expected = config.chatwoot_settings()["webhook_secret"]
    if not config.chatwoot_configured() or len(expected) < config.CHATWOOT_WEBHOOK_SECRET_MIN:
        raise HTTPException(status_code=404, detail="Not Found")
    if not hmac.compare_digest(secret.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        body = json.loads(await request.body())
    except ValueError:
        return Response(status_code=200)
    if isinstance(body, dict):
        background.add_task(handle_event, body)  # after the 200: sends can retry for seconds
    return Response(status_code=200)

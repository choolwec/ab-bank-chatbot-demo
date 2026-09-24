"""Facebook Messenger adapter (tickets M2, M4, M5; research §5.2).

  GET  /webhooks/messenger   verify-token handshake
  POST /webhooks/messenger   X-Hub-Signature-256 over the raw body; messages,
                             quick replies and postbacks -> the durable inbox;
                             echoes and handover events handled inline; 200 now.

The PSID is the user key (hashed in the audit log, sealed for replies).
Replies are plain text + quick replies (render.messenger), never a button
template.

Handover (M4): "Talk to a person" creates a handoff ticket, passes thread
control to the Page Inbox (app 263902037430900) and pauses the bot. An echo of
a message sent by ANOTHER app (a person replying from the inbox) also pauses
it. Control comes back when the agent marks the conversation Done (Meta sends
pass_thread_control back to us) or after HANDOVER_HOURS.

Comments (M5): a comment on a Page post that the S1 scan flags as urgent gets
ONE private reply with the fraud / complaint entry point. A public reply is
posted only with comms-approved wording, and only when the PO turns on
MESSENGER_PUBLIC_REPLIES.
"""

import datetime as dt
import hashlib
import hmac
import json
import time

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse

from .. import audit, config, guards, metrics, render
from ..identity import user_hash
from ..inbox import inbox
from ..messages import msg
from .base import InboundMessage

api = APIRouter()
NAME = "messenger"
MOCK_OUTBOX = "messenger_outbox_mock.jsonl"
MAX_ATTEMPTS = 5
PAGE_INBOX_APP_ID = "263902037430900"  # [VERIFY] against current conversation-routing docs
HANDOVER_HOURS = 24
COMMENT_WINDOW_DAYS = 7


def signature_ok(raw: bytes, header: str | None, secret: str) -> bool:
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


# --- M2: parsing -----------------------------------------------------------------

def parse(body: dict) -> tuple[list[InboundMessage], list[dict]]:
    """Webhook body -> (messages for the inbox, control events handled inline).

    Control events: {"type": "echo", "psid", "app_id"} (a message the Page
    sent), {"type": "thread_back", "psid"} (control returned to us)."""
    messages, events = [], []
    our_app = config.ms_settings()["app_id"]
    for entry in body.get("entry", []):
        for ev in entry.get("messaging", []) + entry.get("standby", []):
            psid = str(ev.get("sender", {}).get("id", ""))
            ts = ev.get("timestamp")
            ts = float(ts) / 1000 if ts else None
            message = ev.get("message") or {}
            if message.get("is_echo"):
                # the Page sent this; "sender" is the Page, the customer is the recipient
                customer = str(ev.get("recipient", {}).get("id", ""))
                events.append({"type": "echo", "psid": customer, "app_id": str(message.get("app_id") or "")})
                continue
            control = ev.get("pass_thread_control") or ev.get("take_thread_control")
            if control is not None:
                new_owner = str(control.get("new_owner_app_id") or "")
                if ev.get("pass_thread_control") and (not our_app or new_owner == our_app):
                    events.append({"type": "thread_back", "psid": psid})
                continue
            inbound = InboundMessage(channel=NAME, user_key=psid, msg_id=message.get("mid"), ts=ts)
            if "postback" in ev:
                inbound.payload = ev["postback"].get("payload")
                inbound.msg_id = ev["postback"].get("mid") or f"pb:{psid}:{ts}"
            elif message.get("quick_reply"):
                inbound.payload = message["quick_reply"].get("payload")
            elif message.get("text"):
                inbound.text = message["text"]
            elif message.get("attachments"):
                att = message["attachments"][0]
                kind = att.get("type")
                coords = (att.get("payload") or {}).get("coordinates")
                if kind == "location" and coords:
                    inbound.location = (float(coords["lat"]), float(coords["long"]))
                else:
                    inbound.media_type = {"file": "document"}.get(kind, kind or "unsupported")
            else:
                continue  # reads, deliveries, reactions
            if "standby" in entry and ev in entry["standby"]:
                inbound.kind = "standby"  # arrived while a person has the thread
            messages.append(inbound)
        # M5: comments on Page posts
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if change.get("field") == "feed" and value.get("item") == "comment" and value.get("verb") == "add":
                author = str((value.get("from") or {}).get("id", ""))
                if author and author == config.ms_settings()["page_id"]:
                    continue  # the Page's own comment
                messages.append(InboundMessage(
                    channel=NAME, user_key=author, text=value.get("message", ""),
                    msg_id=f"comment:{value.get('comment_id')}", ts=float(value.get("created_time") or 0) or None,
                    kind="comment", ref=value.get("comment_id"),
                ))
    return messages, events


# --- M2: webhook routes ------------------------------------------------------------

@api.get("/webhooks/messenger")
def verify(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    expected = config.ms_settings()["verify_token"]
    if hub_mode == "subscribe" and expected and hmac.compare_digest(hub_token, expected):
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="forbidden")


@api.post("/webhooks/messenger")
async def webhook(request: Request):
    raw = await request.body()
    if not signature_ok(raw, request.headers.get("x-hub-signature-256"), config.ms_settings()["app_secret"]):
        raise HTTPException(status_code=401, detail="bad signature")
    try:
        body = json.loads(raw)
    except ValueError:
        return Response(status_code=200)
    messages, events = parse(body)
    for event in events:
        handle_control_event(event)
    stored = sum(inbox.store(m) for m in messages)
    if stored:
        from ..worker import worker

        worker.notify()
    return Response(status_code=200)


# --- M4: handover control ------------------------------------------------------------

def _session_key(psid: str) -> str:
    return f"{NAME}:{user_hash(f'{NAME}:{psid}')}"


def handle_control_event(event: dict, store=None) -> None:
    from ..session import store as default_store

    store = store or default_store
    our_app = config.ms_settings()["app_id"]
    with store.session(_session_key(event["psid"]), NAME) as (session, _):
        if event["type"] == "echo" and event["app_id"] and event["app_id"] != our_app:
            # A person replied from the Page Inbox: stay quiet while they help.
            pause(session)
            audit.log_event(session.id, "system", "human replied in page inbox", action="human_reply",
                            channel=NAME, user_hash=session.user_hash)
        elif event["type"] == "thread_back":
            resume_bot(session)
            audit.log_event(session.id, "system", "thread control returned", action="bot_resumed",
                            channel=NAME, user_hash=session.user_hash)


def pause(session, hours: float = HANDOVER_HOURS) -> None:
    session.bot_paused_until = max(session.bot_paused_until, time.time() + hours * 3600)


def resume_bot(session) -> None:
    session.bot_paused_until = 0.0
    session.slots.pop("handoff_requested", None)


# --- sending ---------------------------------------------------------------------------

class MessengerSender:
    name = NAME

    def __init__(self, transport=None, sleep=time.sleep) -> None:
        self._transport = transport
        self._sleep = sleep

    def configured(self) -> bool:
        return bool(config.ms_settings()["page_token"])

    def _post(self, path: str, body: dict, recipient: str) -> bool:
        if not self.configured():
            record = dict(body, path=path, recipient_hash=user_hash(f"{NAME}:{recipient}"),
                          at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
            record.pop("recipient", None)
            with (config.DATA_DIR / MOCK_OUTBOX).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            return True
        url = f"{config.GRAPH_BASE_URL}/{config.WA_GRAPH_VERSION}/{path}"
        params = {"access_token": config.ms_settings()["page_token"]}
        last_error = ""
        with httpx.Client(transport=self._transport, timeout=10) as client:
            for attempt in range(MAX_ATTEMPTS):
                try:
                    response = client.post(url, json=body, params=params)
                except httpx.HTTPError as exc:
                    last_error = type(exc).__name__
                else:
                    if response.status_code < 300:
                        metrics.record_send(NAME, True)
                        return True
                    last_error = f"HTTP {response.status_code}"
                    if response.status_code != 429 and response.status_code < 500:
                        break
                if attempt < MAX_ATTEMPTS - 1:
                    self._sleep(0.5 * 2 ** attempt)
        metrics.record_send(NAME, False)
        audit.log_event("-", "system", f"send failed: {last_error}", action="send_failed",
                        channel=NAME, user_hash=user_hash(f"{NAME}:{recipient}"))
        return False

    def mark_read(self, message: InboundMessage) -> None:
        for action in ("mark_seen", "typing_on"):
            self._post("me/messages", {"recipient": {"id": message.user_key}, "sender_action": action},
                       message.user_key)

    def send(self, user_key: str, replies: list[dict], session=None) -> bool:
        ok = True
        for message in render.render("messenger", replies):
            ok &= self._post("me/messages", {"recipient": {"id": user_key}, "messaging_type": "RESPONSE",
                                             "message": message}, user_key)
        if session is not None and session.slots.get("handoff_requested"):
            ok &= self.pass_to_inbox(user_key, session)
        return ok

    def send_free_form(self, user_key: str, replies: list[dict], session) -> bool:
        """A reply outside an inbound turn: only inside the 24-h window."""
        from .whatsapp import WindowClosed, window_open

        if not window_open(session):
            raise WindowClosed()
        return self.send(user_key, replies, session=None)

    def pass_to_inbox(self, user_key: str, session) -> bool:
        """M4: hand the conversation to the Page Inbox and pause the bot."""
        session.slots.pop("handoff_requested", None)
        pause(session)
        return self._post("me/pass_thread_control", {
            "recipient": {"id": user_key},
            "target_app_id": PAGE_INBOX_APP_ID,
            "metadata": "customer asked for a person",
        }, user_key)

    def private_reply(self, comment_id: str, text: str, author: str) -> bool:
        """M5: one private message to the author of a public comment."""
        return self._post("me/messages", {"recipient": {"comment_id": comment_id}, "message": {"text": text}},
                          author)

    def public_reply(self, comment_id: str, text: str, author: str) -> bool:
        return self._post(f"{comment_id}/comments", {"message": text}, author)


sender = MessengerSender()


# --- M5: comments -------------------------------------------------------------------------

def handle_comment(message: InboundMessage) -> dict:
    """Decide and send the private reply for one comment. Returns what was done."""
    if message.ts and time.time() - message.ts > COMMENT_WINDOW_DAYS * 86400:
        return {"action": "comment_too_old"}
    masked, _ = guards.mask(guards.clean(message.text or ""))
    signal = guards.urgent_scan(masked)
    if signal is None and not guards.urgent_negated(masked):
        from .. import urgent_model

        if urgent_model.flags(masked):  # N7's second net, as a soft signal
            signal = guards.UrgentSignal("fraud", guards._fraud_sub(masked), "soft")
    who = user_hash(f"{NAME}:{message.user_key}")
    if not signal:
        audit.log_event("-", "system", "comment (not urgent)", action="comment_ignored",
                        channel=NAME, user_hash=who)
        return {"action": "comment_ignored"}
    key = "comment_private.fraud" if signal.kind == "fraud" else "comment_private.complaint"
    sender.private_reply(message.ref, msg(key).format_map(_Contacts()), message.user_key)
    audit.log_event("-", "system", f"private reply sent ({signal.kind}, {signal.strength})",
                    action=f"comment_private:{signal.kind}", channel=NAME, user_hash=who)
    if config.flag("MESSENGER_PUBLIC_REPLIES", False):
        sender.public_reply(message.ref, msg("comment_public"), message.user_key)
    return {"action": f"comment_private:{signal.kind}"}


class _Contacts(dict):
    def __init__(self):
        super().__init__(config.CONTACTS)

    def __missing__(self, key):
        return "{" + key + "}"

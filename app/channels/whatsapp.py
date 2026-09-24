"""WhatsApp Cloud API adapter (tickets W2-W4, W7, W8).

  GET  /webhooks/whatsapp   verify-token handshake (constant-time compare)
  POST /webhooks/whatsapp   X-Hub-Signature-256 over the RAW body -> 401 on
                            failure; statuses logged; messages written to the
                            durable inbox; 200 returned immediately. The
                            worker (worker.py) does the rest.

Parsing (W3): text, interactive button/list replies, template quick-reply
buttons, location, media (image/document/audio/video/sticker) and statuses.
The user key is the BSUID `user_id` when present, else `wa_id`. A phone
number the platform provides goes only to the contact prefill (the customer
confirms it) and is never logged raw.

Sending (W4): read receipt + typing indicator, then the rendered messages.
429 and 5xx are retried with exponential backoff (at most 5 attempts);
permanent failures are written to the audit log. With no credentials set the
adapter runs in MOCK mode, appending to data/whatsapp_outbox_mock.jsonl with
a hashed recipient, so demos and tests need no Meta account.

Free-form sends outside the customer's 24-h window are refused (W8); staff use
an approved template instead (W7).

Coexistence (W11): staff keep the WhatsApp Business app on the same number.
An echo of a message a person sent from the app (the smb_message_echoes
field) passes the same signature check and durable inbox as any other event,
as an InboundMessage with kind "echo"; the worker then pauses the bot for
that customer (app/channels/coexistence.py).

Handoff (H2): with the agent desk (Chatwoot) configured, "Talk to a person"
puts the conversation on the desk (pass_to_desk) and pauses the bot; agents'
replies come back through send_free_form(). See app/desk/bridge.py.
"""

import datetime as dt
import hashlib
import hmac
import json
import re
import time

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse

from .. import audit, config, metrics, render
from ..identity import user_hash
from ..inbox import inbox
from ..messages import button, msg
from .base import InboundMessage

api = APIRouter()
NAME = "whatsapp"
MOCK_OUTBOX = "whatsapp_outbox_mock.jsonl"
MAX_ATTEMPTS = 5
MEDIA_TYPES = {"image", "document", "audio", "video", "sticker", "voice"}
_PHONE_RE = re.compile(r"^\+?\d{9,15}$")

# W7: utility templates (wording approved by Legal, L6). Neutral, no links,
# always the reference the customer already has. {{1}} is the reference.
TEMPLATES = {
    "case_received": {"language": "en", "params": ["ref"]},
    "case_update": {"language": "en", "params": ["ref"]},
    "callback_scheduled": {"language": "en", "params": ["ref"]},
}


class WindowClosed(Exception):
    """A free-form message outside the 24-h window: use a template."""


def signature_ok(raw: bytes, header: str | None, secret: str) -> bool:
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


# --- W3: parsing ---------------------------------------------------------------

def _user_key(message: dict, contacts: list[dict]) -> str:
    """The BSUID when Meta sends one, else the wa_id (phone number)."""
    for key in ("user_id", "from_user_id"):
        if message.get(key):
            return str(message[key])
    for contact in contacts:
        if contact.get("user_id") and contact.get("wa_id") == message.get("from"):
            return str(contact["user_id"])
    return str(message.get("from", ""))


def parse(body: dict) -> tuple[list[InboundMessage], list[dict]]:
    """Webhook body -> (messages, statuses)."""
    messages, statuses = [], []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = value.get("contacts", [])
            for m in value.get("messages", []):
                kind = m.get("type")
                inbound = InboundMessage(
                    channel=NAME,
                    user_key=_user_key(m, contacts),
                    msg_id=m.get("id"),
                    ts=float(m["timestamp"]) if m.get("timestamp") else None,
                )
                wa_id = m.get("from") or ""
                if _PHONE_RE.match(wa_id):
                    inbound.phone_hint = wa_id
                if kind == "text":
                    inbound.text = m.get("text", {}).get("body", "")
                elif kind == "interactive":
                    inter = m.get("interactive", {})
                    reply = inter.get("button_reply") or inter.get("list_reply") or {}
                    inbound.payload = reply.get("id")
                elif kind == "button":  # a template's quick-reply button
                    inbound.payload = m.get("button", {}).get("payload") or None
                    if not inbound.payload:
                        inbound.text = m.get("button", {}).get("text")
                elif kind == "location":
                    loc = m.get("location", {})
                    if "latitude" in loc and "longitude" in loc:
                        inbound.location = (float(loc["latitude"]), float(loc["longitude"]))
                elif kind in MEDIA_TYPES:
                    inbound.media_type = kind
                    # a caption is text the customer typed: it goes through guards
                    caption = (m.get(kind) or {}).get("caption")
                    if caption:
                        inbound.text = caption
                elif kind in ("reaction", "system", "ephemeral"):
                    continue
                else:  # contacts, unsupported, ...
                    inbound.media_type = kind or "unsupported"
                messages.append(inbound)
            for echo in value.get("message_echoes", []):
                inbound = parse_echo(echo, contacts)
                if inbound is not None:
                    messages.append(inbound)
            for st in value.get("statuses", []):
                statuses.append({
                    "status": st.get("status"),
                    "id": st.get("id"),
                    "recipient": st.get("recipient_id") or st.get("recipient_user_id") or "",
                    "errors": [e.get("code") for e in st.get("errors", [])],
                })
    return messages, statuses


def parse_echo(echo: dict, contacts: list[dict] | None = None) -> InboundMessage | None:
    """W11: one smb_message_echoes item, i.e. a message a PERSON sent from the
    WhatsApp Business app on our number (coexistence). [VERIFY] the exact
    shape against Meta's current coexistence docs. Modelled as
      {"from": <our number>, "to": <customer wa_id>, "to_user_id": <BSUID>?,
       "id": "wamid...", "timestamp": "...", "type": "text", "text": {...}}
    Only WHO it went to matters (the same user key as the customer's own
    messages: the BSUID when present, else the wa_id), plus its id and time
    for de-duplication. The staff member's text is never read or stored."""
    customer = echo.get("to_user_id") or echo.get("recipient_user_id")
    for contact in contacts or []:
        if not customer and contact.get("user_id") and contact.get("wa_id") == echo.get("to"):
            customer = contact["user_id"]
    customer = customer or echo.get("to")
    if not customer:
        return None
    return InboundMessage(
        channel=NAME,
        user_key=str(customer),
        msg_id=f"echo:{echo['id']}" if echo.get("id") else None,
        ts=float(echo["timestamp"]) if echo.get("timestamp") else None,
        kind="echo",
    )


def log_statuses(statuses: list[dict]) -> None:
    """Delivery metrics (sent/delivered/read/failed). Hashed recipient only."""
    for st in statuses:
        who = user_hash(f"{NAME}:{st['recipient']}") if st["recipient"] else None
        detail = f"status {st['status']}" + (f" errors={st['errors']}" if st["errors"] else "")
        audit.log_event("-", "system", detail, action=f"wa_status:{st['status']}",
                        channel=NAME, user_hash=who)


# --- W2: webhook routes ----------------------------------------------------------

@api.get("/webhooks/whatsapp")
def verify(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    expected = config.wa_settings()["verify_token"]
    if hub_mode == "subscribe" and expected and hmac.compare_digest(hub_token, expected):
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="forbidden")


@api.post("/webhooks/whatsapp")
async def webhook(request: Request):
    raw = await request.body()
    if not signature_ok(raw, request.headers.get("x-hub-signature-256"), config.wa_settings()["app_secret"]):
        raise HTTPException(status_code=401, detail="bad signature")
    try:
        body = json.loads(raw)
    except ValueError:
        return Response(status_code=200)  # nothing we can use; don't make Meta retry
    messages, statuses = parse(body)
    log_statuses(statuses)
    stored = sum(inbox.store(m) for m in messages)  # durable write BEFORE the ack
    if stored:
        from ..worker import worker

        worker.notify()
    return Response(status_code=200)


# --- W4: sending -------------------------------------------------------------------

class WhatsAppSender:
    name = NAME

    def __init__(self, transport=None, sleep=time.sleep) -> None:
        self._transport = transport  # tests inject httpx.MockTransport
        self._sleep = sleep

    def configured(self) -> bool:
        s = config.wa_settings()
        return bool(s["token"] and s["phone_number_id"])

    def _url(self) -> str:
        s = config.wa_settings()
        return f"{config.GRAPH_BASE_URL}/{config.WA_GRAPH_VERSION}/{s['phone_number_id']}/messages"

    def _post(self, body: dict, recipient: str) -> bool:
        """POST with retries. True if Meta accepted it."""
        if not self.configured():
            self._mock(body, recipient)
            return True
        headers = {"Authorization": f"Bearer {config.wa_settings()['token']}"}
        last_error = ""
        with httpx.Client(transport=self._transport, timeout=10) as client:
            for attempt in range(MAX_ATTEMPTS):
                try:
                    response = client.post(self._url(), json=body, headers=headers)
                except httpx.HTTPError as exc:
                    last_error = f"{type(exc).__name__}"
                else:
                    if response.status_code < 300:
                        metrics.record_send(NAME, True)
                        return True
                    last_error = f"HTTP {response.status_code}"
                    if response.status_code != 429 and response.status_code < 500:
                        break  # a permanent error: retrying won't help
                if attempt < MAX_ATTEMPTS - 1:
                    self._sleep(0.5 * 2 ** attempt)
        metrics.record_send(NAME, False)
        audit.log_event("-", "system", f"send failed: {last_error}", action="send_failed",
                        channel=NAME, user_hash=user_hash(f"{NAME}:{recipient}"))
        return False

    def _mock(self, body: dict, recipient: str) -> None:
        record = dict(body, to=f"hash:{user_hash(f'{NAME}:{recipient}')}",
                      at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        with (config.DATA_DIR / MOCK_OUTBOX).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def mark_read(self, message: InboundMessage) -> None:
        if not message.msg_id:
            return
        self._post({
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message.msg_id,
            "typing_indicator": {"type": "text"},
        }, message.user_key)

    def send(self, user_key: str, replies: list[dict], session=None) -> bool:
        """Render and send the bot's replies to one customer."""
        ok = True
        for body in render.whatsapp_all(replies):
            ok &= self._post(dict({"messaging_product": "whatsapp", "recipient_type": "individual",
                                   "to": user_key}, **body), user_key)
        if session is not None and session.slots.get("handoff_requested"):
            ok &= self.pass_to_desk(user_key, session)
        return ok

    def send_free_form(self, user_key: str, replies: list[dict], session) -> bool:
        """A reply NOT triggered by an inbound message (an agent, W8): only
        inside the customer's 24-h window."""
        if not window_open(session):
            raise WindowClosed()
        return self.send(user_key, replies)

    def pass_to_desk(self, user_key: str, session) -> bool:
        """H2: put the conversation on the agent desk (Chatwoot) and pause the
        bot, like Messenger's pass_to_inbox(). `user_key` only derives the
        hashed session key an agent's reply comes back to; Chatwoot never sees
        it."""
        from .. import router
        from ..desk import bridge

        ref = session.slots.pop("handoff_requested", None)
        if bridge.open_conversation(session, f"{NAME}:{user_hash(f'{NAME}:{user_key}')}", ref):
            return True
        # Concern #13: the customer was just told a person will reply here,
        # but nobody is watching and the bot is not paused. Say so, once.
        replies, _ = router.respond(session, [{
            "text": msg("handoff_desk_failed", ref=ref or ""),
            "buttons": [button("request_a_callback", router.REQUEST_CALLBACK), button("main_menu", "menu")],
        }], {"intent": "human_handoff", "action": "handoff_desk_failed"})
        self.send(user_key, replies)
        return False

    def send_template(self, user_key: str, name: str, **params) -> bool:
        """W7: an approved utility template, allowed outside the window."""
        spec = TEMPLATES[name]
        values = [str(params[p]) for p in spec["params"]]
        return self._post({
            "messaging_product": "whatsapp",
            "to": user_key,
            "type": "template",
            "template": {
                "name": name,
                "language": {"code": spec["language"]},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": v} for v in values]}],
            },
        }, user_key)


def window_open(session, now: float | None = None) -> bool:
    now = now or time.time()
    return bool(session.last_inbound_at) and now - session.last_inbound_at < config.CUSTOMER_WINDOW_HOURS * 3600


sender = WhatsAppSender()

"""Thin client for the Chatwoot Application API (tickets H2, H4).

Every request carries the `api_access_token` header: the access token of the
agent (or agent bot) the integration acts as [VERIFY which token the chosen
Chatwoot version accepts for creating contacts, conversations and incoming
messages]. Endpoints, all under /api/v1/accounts/{CHATWOOT_ACCOUNT_ID}:

  GET  contacts/search?q=<identifier>   find our contact (exact identifier match)
  POST contacts                         create it: identifier, name if given
  POST conversations                    open one in the API-channel inbox
  POST conversations/{id}/messages      a private note, or a customer message
                                        forwarded with message_type incoming
  GET  conversations?labels[]=&status=  conversations with a label (H4)
  GET  conversations/{id}/messages      one conversation's messages (H4)

Request fields and response shapes come from Chatwoot's public API docs, not
a running instance; each is marked [VERIFY] below. The caller (bridge.py)
minimises what is sent: a hashed identifier, a name only if the customer gave
one, and masked text. Never a phone number, BSUID or PSID. Errors carry only
the HTTP status, never the request body.
"""

import datetime as dt
import time

import httpx

from .. import config

MAX_ATTEMPTS = 3
TIMEOUT_SECONDS = 10
MAX_PAGES = 20  # listing safety cap: 20 pages of Chatwoot's 25 [VERIFY page size]


class ChatwootError(Exception):
    """Chatwoot is unreachable, refused the request, or answered oddly."""


def _payload(data):
    """Chatwoot wraps most responses as {"payload": ...} [VERIFY]."""
    return data.get("payload", data) if isinstance(data, dict) else data


def _as_list(data) -> list:
    """A list response: {"payload": [...]} or {"data": {"payload": [...]}}."""
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    items = _payload(data)
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def conversation_id(obj: dict):
    """The conversation number used in API paths. Chatwoot serialises it as
    `id`, and some payloads also carry `display_id` [VERIFY]: prefer that."""
    return obj.get("display_id") or obj.get("id")


def timestamp(value) -> float:
    """Chatwoot timestamps are unix seconds, or ISO strings in some payloads."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value:
        try:
            return float(value)
        except ValueError:
            pass
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


class ChatwootClient:
    def __init__(self, transport=None, sleep=time.sleep) -> None:
        self._transport = transport  # tests inject httpx.MockTransport
        self._sleep = sleep

    def configured(self) -> bool:
        return config.chatwoot_configured()

    def _base(self) -> str:
        s = config.chatwoot_settings()
        return f"{s['url']}/api/v1/accounts/{s['account_id']}"

    def _request(self, method: str, path: str, json=None, params=None):
        """One call, retried on 429, 5xx and network errors."""
        if not self.configured():
            raise ChatwootError("not configured")
        headers = {"api_access_token": config.chatwoot_settings()["token"]}  # [VERIFY] header name
        last_error = ""
        with httpx.Client(transport=self._transport, timeout=TIMEOUT_SECONDS) as client:
            for attempt in range(MAX_ATTEMPTS):
                try:
                    response = client.request(method, self._base() + path, json=json, params=params,
                                              headers=headers)
                except httpx.HTTPError as exc:
                    last_error = type(exc).__name__
                else:
                    if response.status_code < 300:
                        try:
                            return response.json() if response.content else {}
                        except ValueError:
                            raise ChatwootError("response is not JSON") from None
                    last_error = f"HTTP {response.status_code}"
                    if response.status_code != 429 and response.status_code < 500:
                        break  # a permanent error: retrying won't help
                if attempt < MAX_ATTEMPTS - 1:
                    self._sleep(0.5 * 2 ** attempt)
        raise ChatwootError(last_error)

    def _inbox_id(self):
        raw = config.chatwoot_settings()["inbox_id"]
        return int(raw) if raw.isdigit() else raw

    # --- contacts ------------------------------------------------------------------

    def find_contact(self, identifier: str) -> dict | None:
        # search matches name, email, phone and identifier [VERIFY]; keep exact hits only
        found = self._request("GET", "/contacts/search", params={"q": identifier})
        return next((c for c in _as_list(found) if c.get("identifier") == identifier), None)

    def create_contact(self, identifier: str, name: str | None = None) -> dict:
        body = {"identifier": identifier}
        if name:
            body["name"] = name
        data = _payload(self._request("POST", "/contacts", json=body))
        # {"payload": {"contact": {...}, "contact_inbox": {...}}} [VERIFY]
        contact = data.get("contact", data) if isinstance(data, dict) else None
        if not isinstance(contact, dict) or not contact.get("id"):
            raise ChatwootError("unexpected contact response")
        return contact

    def ensure_contact(self, identifier: str, name: str | None = None) -> int:
        """Look the contact up by identifier; create it if it isn't there."""
        contact = self.find_contact(identifier)
        if contact is None:
            try:
                contact = self.create_contact(identifier, name)
            except ChatwootError:
                contact = self.find_contact(identifier)  # created meanwhile (a 422)
                if contact is None:
                    raise
        return int(contact["id"])

    # --- conversations and messages ---------------------------------------------------

    def create_conversation(self, contact_id: int, source_id: str, custom_attributes: dict):
        """Open a conversation in the API-channel inbox. With contact_id and
        inbox_id Chatwoot finds or creates the contact's inbox link itself,
        keyed by source_id (we pass the hashed user key) [VERIFY]."""
        data = self._request("POST", "/conversations", json={
            "inbox_id": self._inbox_id(),
            "contact_id": contact_id,
            "source_id": source_id,
            "status": "open",
            "custom_attributes": custom_attributes,  # [VERIFY] accepted on create
        })
        conv = conversation_id(data) if isinstance(data, dict) else None
        if not conv:
            raise ChatwootError("unexpected conversation response")
        return conv

    def post_message(self, conv, content: str, *, incoming: bool = False, private: bool = False) -> dict:
        # message_type "incoming" is accepted only in API-channel inboxes [VERIFY]
        return self._request("POST", f"/conversations/{conv}/messages", json={
            "content": content,
            "message_type": "incoming" if incoming else "outgoing",
            "private": private,
        })

    def private_note(self, conv, content: str) -> dict:
        """Staff-only: agents see it, the customer never does."""
        return self.post_message(conv, content, private=True)

    def forward_incoming(self, conv, content: str) -> dict:
        """A customer's message, shown on the desk as if they had typed it there."""
        return self.post_message(conv, content, incoming=True)

    # --- H4: labelled conversations ------------------------------------------------------

    def labelled_conversations(self, label: str, since: float) -> list[dict]:
        """Conversations carrying `label`, with activity since `since` (unix)."""
        out, seen = [], set()
        for page in range(1, MAX_PAGES + 1):
            batch = _as_list(self._request("GET", "/conversations", params={
                "labels[]": label, "status": "all", "page": page}))  # [VERIFY] labels filter
            new = [c for c in batch if conversation_id(c) not in seen]
            if not new:
                break
            for c in new:
                seen.add(conversation_id(c))
                active = max(timestamp(c.get(k)) for k in ("last_activity_at", "timestamp", "created_at"))
                if active >= since:
                    out.append(c)
        return out

    def conversation_messages(self, conv) -> list[dict]:
        """Every message, oldest first. Chatwoot pages backwards with
        ?before=<message id> [VERIFY]."""
        out, seen, before = [], set(), None
        for _ in range(MAX_PAGES):
            params = {"before": before} if before else None
            batch = _as_list(self._request("GET", f"/conversations/{conv}/messages", params=params))
            new = [m for m in batch if m.get("id") not in seen]
            if not new:
                break
            seen.update(m.get("id") for m in new)
            out = new + out
            ids = [m["id"] for m in new if isinstance(m.get("id"), int)]
            if not ids:
                break
            before = min(ids)
        return sorted(out, key=lambda m: (timestamp(m.get("created_at")), m.get("id") or 0))


client = ChatwootClient()

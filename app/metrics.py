"""In-memory operational counters for /health (ticket R1).

Two rolling one-hour counts, both COUNTS ONLY -- no ids, no text, nothing
about a customer:

  webhook_responses  every /webhooks/* response by status class ("2xx",
                     "4xx", "5xx"), plus "signed_4xx": a request that carried
                     Meta's X-Hub-Signature-256 header and was still refused
                     (a wrong app secret after a rotation looks like this)
  sends              every call to Meta's send API by channel and outcome
                     ("whatsapp:ok", "messenger:failed"); mock sends are not
                     counted, so the numbers only ever describe Meta

In memory by design, like the rate-limit buckets: one process (CLAUDE.md),
and a restart simply starts a new hour. The alert script reads them through
GET /health, because only the running app can see them.
"""

import threading
import time
from collections import Counter

BUCKET_SECONDS = 60


class RollingCounter:
    """Counts per key over the last `window` seconds, in one-minute buckets,
    so memory stays bounded (at most window/60 buckets) whatever the traffic."""

    def __init__(self, window: int = 3600, clock=time.time) -> None:
        self.window = window
        self._clock = clock
        self._buckets: dict[int, Counter] = {}
        self._lock = threading.Lock()

    def add(self, key: str, n: int = 1) -> None:
        minute = int(self._clock() // BUCKET_SECONDS)
        with self._lock:
            self._buckets.setdefault(minute, Counter())[key] += n
            self._prune(minute)

    def counts(self) -> dict[str, int]:
        minute = int(self._clock() // BUCKET_SECONDS)
        total = Counter()
        with self._lock:
            self._prune(minute)
            for bucket in self._buckets.values():
                total.update(bucket)
        return dict(total)

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()

    def _prune(self, minute: int) -> None:
        oldest = minute - self.window // BUCKET_SECONDS + 1
        for m in [m for m in self._buckets if m < oldest]:
            del self._buckets[m]


webhook_responses = RollingCounter()
sends = RollingCounter()


def record_send(channel: str, ok: bool) -> None:
    sends.add(f"{channel}:{'ok' if ok else 'failed'}")


def _record_webhook(status: int, signed: bool) -> None:
    webhook_responses.add(f"{status // 100}xx")
    if signed and 400 <= status < 500:
        webhook_responses.add("signed_4xx")


class WebhookStatusMiddleware:
    """Pure ASGI middleware: counts /webhooks/* responses by status class.
    An exception that escapes the route counts as a 5xx (the server error
    handler outside us turns it into a 500) and is re-raised unchanged."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/webhooks/"):
            await self.app(scope, receive, send)
            return
        signed = any(name == b"x-hub-signature-256" for name, _ in scope.get("headers", []))
        seen = {}

        async def _send(message):
            if message["type"] == "http.response.start":
                seen["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception:
            _record_webhook(seen.get("status", 500), signed)
            raise
        if "status" in seen:
            _record_webhook(seen["status"], signed)

"""Sliding-window rate limits (§3.3, ticket P4).

Two limiters, because the channels arrive differently:
  per IP    for /chat -- the widget talks to us directly.
  per user  for webhooks -- every WhatsApp and Messenger message arrives from
            Meta's own IP addresses, so a per-IP limit would throttle every
            customer together. Keyed by the (hashed) user instead.
Both live in process memory, which is one reason the app runs as exactly one
process (see CLAUDE.md).
"""

import time
from collections import defaultdict, deque

from fastapi import Request

from . import config


class SlidingWindowLimiter:
    def __init__(self, limit_fn, window_seconds: int = 60) -> None:
        self.limit_fn = limit_fn  # read per call, so config changes apply live
        self.window = window_seconds
        self.hits: dict[str, deque] = defaultdict(deque)
        self.reported: dict[str, float] = {}  # key -> when first_refusal() last said yes

    def limited(self, key: str) -> bool:
        now = time.time()
        if len(self.hits) > 1024:  # shed buckets idle past the window (scanner churn)
            for k in [k for k, w in self.hits.items() if not w or now - w[-1] > self.window]:
                del self.hits[k]
            for k in [k for k, t in self.reported.items() if now - t > self.window]:
                del self.reported[k]
        window = self.hits[key]
        while window and now - window[0] > self.window:
            window.popleft()
        if len(window) >= self.limit_fn():
            return True
        window.append(now)
        return False

    def first_refusal(self, key: str) -> bool:
        """True at most once per window for a limited key, so a flood writes
        one audit event a minute rather than one per refused request."""
        now = time.time()
        last = self.reported.get(key)
        if last is not None and now - last <= self.window:
            return False
        self.reported[key] = now
        return True


ip_limiter = SlidingWindowLimiter(lambda: config.RATE_LIMIT_PER_MINUTE)
user_limiter = SlidingWindowLimiter(lambda: config.USER_RATE_LIMIT_PER_MINUTE)


def client_ip(request: Request) -> str:
    """Rate-limit key. Behind a reverse proxy every request arrives from the
    proxy's IP, which would collapse all visitors into one shared bucket —
    set PROXY_HOPS to the number of proxies in front (usually 1) and the real
    client IP is taken from X-Forwarded-For instead. The rightmost `hops`
    entries are the ones our own infrastructure appended; anything left of
    those is client-supplied and untrusted."""
    hops = config.proxy_hops()
    if hops > 0:
        xff = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"

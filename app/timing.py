"""Server-side timing for the load and soak test (ticket P9).

A pure-ASGI middleware times every request by route group (/chat, each
webhook, /health, /admin, /widget, other), and the webhook worker times each
message it processes ("worker:whatsapp"). Samples go into bounded in-memory
windows; `GET /admin/timing` (staff only) reports count, p50, p95, p99 and
max per group, with the inbox queue and the process's memory, so a load
test can read the server's own view on staging or production too, without
a shell on the box. Only durations are kept: no path, body or user.
"""

import math
import threading
import time
from collections import deque

WINDOW = 20_000  # samples kept per group: > 15 minutes at 20 messages/s
EXACT = {"/chat", "/webhooks/whatsapp", "/webhooks/messenger", "/health"}


def group_of(path: str) -> str:
    if path in EXACT:
        return path
    for prefix in ("/admin/", "/widget/"):
        if path.startswith(prefix):
            return prefix.rstrip("/")
    return "other"


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile of already sorted values."""
    if not values:
        return 0.0
    return values[max(0, math.ceil(p / 100 * len(values)) - 1)]


class Timings:
    def __init__(self, window: int = WINDOW) -> None:
        self.window = window
        self._lock = threading.Lock()
        self._samples: dict[str, deque] = {}
        self._counts: dict[str, int] = {}
        self.since = time.time()

    def record(self, group: str, ms: float) -> None:
        with self._lock:
            if group not in self._samples:
                self._samples[group] = deque(maxlen=self.window)
                self._counts[group] = 0
            self._samples[group].append(ms)
            self._counts[group] += 1

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()
            self._counts.clear()
            self.since = time.time()

    def summary(self) -> dict:
        with self._lock:
            snapshot = {g: (sorted(s), self._counts[g]) for g, s in self._samples.items()}
        return {
            group: {
                "count": count,
                "window": len(values),
                "p50_ms": round(percentile(values, 50), 1),
                "p95_ms": round(percentile(values, 95), 1),
                "p99_ms": round(percentile(values, 99), 1),
                "max_ms": round(values[-1], 1) if values else 0.0,
            }
            for group, (values, count) in sorted(snapshot.items())
        }


timings = Timings()


class TimingMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        start = time.perf_counter()
        try:
            await self.app(scope, receive, send)
        finally:
            timings.record(group_of(scope.get("path", "")), (time.perf_counter() - start) * 1000)


def rss_mb() -> float | None:
    """Resident memory of this process (Linux), for the no-growth check."""
    try:
        with open("/proc/self/status", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return None

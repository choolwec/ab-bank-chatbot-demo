"""The single background worker for webhook channels (ticket W2).

Started in main.lifespan. Wakes when a webhook stores a message (notify())
and at least once a second, then processes the inbox in arrival order, one
message at a time -- so a customer's burst ("hi", "I lost my card", "pls
help") is answered in order. In-process by design, matching the "exactly one
process" rule; scaling out means Redis + arq/rq, the same trigger as moving
sessions.
"""

import asyncio
import logging
import time

from .inbox import inbox
from .timing import timings

log = logging.getLogger("abz.worker")


def adapters():
    from .channels import messenger, whatsapp

    return {"whatsapp": whatsapp.sender, "messenger": messenger.sender}


def dispatch(message, findings):
    from .channels import messaging

    start = time.perf_counter()
    try:
        messaging.process(message, findings, adapters()[message.channel])
    finally:  # P9: per-message processing time, read at /admin/timing
        timings.record(f"worker:{message.channel}", (time.perf_counter() - start) * 1000)


def process_now() -> int:
    """Process everything pending, synchronously (tests, admin, shutdown)."""
    return inbox.process_pending(dispatch)


class Worker:
    def __init__(self) -> None:
        self._loop = None
        self._event = None
        self._task = None

    def notify(self) -> None:
        if self._loop and self._event:
            self._loop.call_soon_threadsafe(self._event.set)

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
            self._event.clear()
            try:
                await asyncio.to_thread(process_now)
            except Exception:  # never let the worker die; rows are retried
                log.exception("inbox processing failed")

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._event = asyncio.Event()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None


worker = Worker()

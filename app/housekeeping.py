"""Retention purges, at start-up and every night (ticket R1).

Before R1 the audit and session purges ran only when the app started, and
the webhook inbox was never purged at all. purge_all() is the one place that
runs every retention rule:

  audit.db     events after TRANSCRIPT_RETENTION_DAYS; tickets after
               TICKET_RETENTION_DAYS (0 = kept)
  sessions.db  sessions idle for TRANSCRIPT_RETENTION_DAYS
  inbox.db     processed and failed rows after TRANSCRIPT_RETENTION_DAYS
               (they hold masked message text, like a transcript). Unprocessed
               rows are never purged. A row id also de-duplicates Meta's
               redeliveries, so keep this at least as long as Meta retries a
               webhook [VERIFY: Meta's retry window, documented as up to 7 days].

The Housekeeper runs purge_all() at PURGE_HOUR (Lusaka time) every night,
inside the one app process, like the inbox worker: no cron entry needed.
"""

import asyncio
import datetime as dt
import logging

from . import audit, config, hours
from . import inbox as inbox_mod
from . import session as session_mod

log = logging.getLogger("abz.housekeeping")


def purge_all() -> dict:
    """Every retention purge. Returns counts only (logged, never ids)."""
    purged = audit.purge_expired()
    purged["sessions"] = session_mod.store.purge_expired()
    purged["inbox"] = inbox_mod.inbox.purge(config.TRANSCRIPT_RETENTION_DAYS)
    log.info("retention purge: %s", purged)
    return purged


def seconds_until_next_run(now: dt.datetime | None = None) -> float:
    now = (now or hours.now()).astimezone(hours.LUSAKA)
    target = now.replace(hour=config.PURGE_HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


class Housekeeper:
    def __init__(self) -> None:
        self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(seconds_until_next_run())
            try:
                await asyncio.to_thread(purge_all)
            except Exception:  # never let the loop die; tomorrow tries again
                log.exception("retention purge failed")

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None


housekeeper = Housekeeper()

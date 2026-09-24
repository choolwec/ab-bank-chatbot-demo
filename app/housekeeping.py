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
inside the one app process, like the inbox worker: no cron entry needed. An
invalid PURGE_HOUR falls back to 02:00 with a warning (config.purge_hour()).

At start-up, purge_at_startup() runs the same purge but never stops the app:
a locked or corrupt database is logged (the exception type only, never its
message) and the app starts anyway; the nightly run tries again.

The JiraRetrier (concern #6) runs audit.retry_jira() at start-up and every
JIRA_RETRY_SECONDS: tickets whose Jira copy was lost to a restart or a Jira
outage are pushed again.
"""

import asyncio
import datetime as dt
import logging

from . import audit, config, hours
from . import inbox as inbox_mod
from . import session as session_mod
from .desk.links import links as desk_links

log = logging.getLogger("abz.housekeeping")


def purge_all() -> dict:
    """Every retention purge. Returns counts only (logged, never ids)."""
    purged = audit.purge_expired()
    purged["sessions"] = session_mod.store.purge_expired()
    purged["inbox"] = inbox_mod.inbox.purge(config.TRANSCRIPT_RETENTION_DAYS)
    purged["desk_links"] = desk_links.purge(config.TRANSCRIPT_RETENTION_DAYS)  # H2; no-op when off
    log.info("retention purge: %s", purged)
    return purged


def purge_at_startup() -> dict | None:
    """purge_all() for main.lifespan: a failure is logged, never raised."""
    try:
        return purge_all()
    except Exception as exc:  # noqa: BLE001 -- start-up must go on
        log.error("start-up retention purge failed (%s); starting anyway, the nightly run retries",
                  type(exc).__name__)
        return None


def seconds_until_next_run(now: dt.datetime | None = None) -> float:
    now = (now or hours.now()).astimezone(hours.LUSAKA)
    target = now.replace(hour=config.purge_hour(), minute=0, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


class JiraRetrier:
    def __init__(self) -> None:
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                counts = await asyncio.to_thread(audit.retry_jira)
                if any(counts.values()):
                    log.info("jira retry: %s", counts)
            except Exception as exc:  # noqa: BLE001 -- never let the loop die
                log.error("jira retry failed (%s)", type(exc).__name__)
            await asyncio.sleep(config.JIRA_RETRY_SECONDS)

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
jira_retrier = JiraRetrier()

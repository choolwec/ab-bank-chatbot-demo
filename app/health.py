"""The /health `checks` object (ticket R1).

Each check is a small dict of COUNTS with an `ok` boolean, computed against
the thresholds in config.py. Uptime checkers read `checks.<name>.ok`;
admin/alerts.py turns a failing check into a Teams post and a Jira issue.
Nothing here ever carries an id, a user hash or message text.

  worker_queue        age of the oldest unprocessed webhook message
  failed_messages     messages the worker gave up on (MAX_ATTEMPTS) in the
                      last hour; `urgent` counts those whose masked text reads
                      as a fraud report (guards.urgent_scan), which the alert
                      raises to Sev 1
  send_failures       share of Meta send calls that failed in the last hour
  webhook_errors      share of /webhooks/* responses that were 5xx
  webhook_rejected    signed Meta requests refused with a 4xx (a wrong secret)
  embedding_model     whether the model verified, when a feature needs it

A check that cannot be computed at all (an unreadable inbox.db) raises
ChecksBroken, and /health answers 503: that is "the app itself is broken".
"""

from . import config, embedder, guards, metrics, shadow, urgent_model
from . import inbox as inbox_mod


class ChecksBroken(Exception):
    """A store the app needs could not be read."""

    def __init__(self, checks: dict) -> None:
        super().__init__("health checks could not be computed")
        self.checks = checks


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def worker_queue() -> dict:
    box = inbox_mod.inbox
    age = box.oldest_pending_age()
    return {
        "ok": age <= config.QUEUE_MAX_AGE_SECONDS,
        "oldest_pending_seconds": int(age),
        "pending": box.counts().get("new", 0),
        "threshold_seconds": config.QUEUE_MAX_AGE_SECONDS,
    }


def failed_messages() -> dict:
    texts = inbox_mod.inbox.failed_since(config.HEALTH_WINDOW_MINUTES * 60)
    urgent = 0
    for text in texts:
        signal = guards.urgent_scan(text)
        if signal is not None and signal.kind == "fraud":
            urgent += 1
    return {
        "ok": len(texts) <= config.FAILED_MESSAGES_MAX,
        "count": len(texts),
        "urgent": urgent,
        "threshold": config.FAILED_MESSAGES_MAX,
        "window_minutes": config.HEALTH_WINDOW_MINUTES,
    }


def send_failures() -> dict:
    counts = metrics.sends.counts()
    by_channel = {}
    for key, n in counts.items():
        channel, outcome = key.split(":", 1)
        by_channel.setdefault(channel, {"ok": 0, "failed": 0})[outcome] += n
    failed = sum(c["failed"] for c in by_channel.values())
    attempts = failed + sum(c["ok"] for c in by_channel.values())
    rate = _rate(failed, attempts)
    return {
        "ok": rate <= config.SEND_FAILURE_MAX_RATE,
        "attempts": attempts,
        "failed": failed,
        "rate": rate,
        "threshold": config.SEND_FAILURE_MAX_RATE,
        "window_minutes": config.HEALTH_WINDOW_MINUTES,
        "by_channel": by_channel,
    }


def webhook_errors() -> dict:
    counts = metrics.webhook_responses.counts()
    by_class = {k: counts.get(k, 0) for k in ("2xx", "3xx", "4xx", "5xx")}
    requests = sum(by_class.values())
    rate = _rate(by_class["5xx"], requests)
    return {
        "ok": rate <= config.WEBHOOK_5XX_MAX_RATE,
        "requests": requests,
        "count_5xx": by_class["5xx"],
        "count_4xx": by_class["4xx"],
        "rate": rate,
        "threshold": config.WEBHOOK_5XX_MAX_RATE,
        "window_minutes": config.HEALTH_WINDOW_MINUTES,
    }


def webhook_rejected() -> dict:
    count = metrics.webhook_responses.counts().get("signed_4xx", 0)
    return {
        "ok": count <= config.WEBHOOK_REJECTED_MAX,
        "count": count,
        "threshold": config.WEBHOOK_REJECTED_MAX,
        "window_minutes": config.HEALTH_WINDOW_MINUTES,
    }


_verified_once = None


def _model_verified(needed: bool) -> bool:
    """When a feature needs the model, the embedder's own cached load (it
    loads once per process). Otherwise hash the files once per process, not
    once a minute: they cannot change under a running app."""
    global _verified_once
    if needed:
        return embedder.available()
    if _verified_once is None:
        _verified_once = embedder.verify()
    return _verified_once


def embedding_model() -> dict:
    needed_by = [name for name, on in (
        ("EMBEDDINGS_ENABLED", config.embeddings_enabled()),
        ("URGENT_MODEL_ENABLED", urgent_model.enabled()),
        ("SHADOW_MATCHER", shadow.enabled()),
    ) if on]
    verified = _model_verified(bool(needed_by))
    return {"ok": verified or not needed_by, "verified": verified, "needed_by": needed_by}


CHECKS = {
    "worker_queue": worker_queue,
    "failed_messages": failed_messages,
    "send_failures": send_failures,
    "webhook_errors": webhook_errors,
    "webhook_rejected": webhook_rejected,
    "embedding_model": embedding_model,
}


def checks() -> dict:
    """Every check. Raises ChecksBroken (carrying the partial result) when
    any of them could not be computed."""
    out, broken = {}, False
    for name, check in CHECKS.items():
        try:
            out[name] = check()
        except Exception:  # an unreadable store; never leak the error text
            out[name] = {"ok": False, "error": "unavailable"}
            broken = True
    if broken:
        raise ChecksBroken(out)
    return out

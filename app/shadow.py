"""Shadow mode for the embedding matcher (ticket N4).

With SHADOW_MATCHER on, customers are answered exactly as today (the
character matcher), while every free-text message is ALSO scored by the
hybrid matcher. Both decisions are written to the audit log as one
`action=shadow` event -- intents, scores and decisions only; the masked
customer text is already in the preceding user event -- so
`python -m admin.shadow_report --days 7` can list the disagreements for the
weekly review. Never affects a reply; never raises.
"""

import json
import logging

from . import audit, config

log = logging.getLogger("abz.shadow")
_matcher = None
_tried = False


def enabled() -> bool:
    return config.flag("SHADOW_MATCHER", False)


def _hybrid():
    global _matcher, _tried
    if not _tried:
        _tried = True
        from .matcher import Matcher

        m = Matcher(use_embeddings=True)
        _matcher = m if m.mode == "hybrid" else None
    return _matcher


def decision(ranked, abstain=("out_of_scope",)) -> tuple[str, str | None, float]:
    """(decision, intent, score) exactly as the router's confidence gate."""
    if not ranked:
        return "fallback", None, 0.0
    top, score = ranked[0]
    if top in abstain and score >= config.MEDIUM_CONFIDENCE:
        return "out_of_scope", top, score
    if score >= config.HIGH_CONFIDENCE:
        return "answer", top, score
    if score >= config.MEDIUM_CONFIDENCE:
        return "did_you_mean", top, score
    return "fallback", top, score


def observe(session, text, live_ranked) -> None:
    if not enabled():
        return
    try:
        hybrid = _hybrid()
        if hybrid is None:
            return
        live = decision(live_ranked)
        shadow = decision(hybrid.match(text))
        record = {
            "live": {"decision": live[0], "intent": live[1], "score": round(live[2], 3)},
            "shadow": {"decision": shadow[0], "intent": shadow[1], "score": round(shadow[2], 3)},
            "agree": live[:2] == shadow[:2],
        }
        audit.log_event(session.id, "system", json.dumps(record), action="shadow",
                        channel=session.channel, user_hash=session.user_hash)
    except Exception:  # shadow mode must never affect a customer
        log.exception("shadow scoring failed")

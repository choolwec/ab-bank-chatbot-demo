"""Processing for webhook channels -- WhatsApp and Messenger (W2, W5, W6, W8,
P4, research §7.4). The worker calls process() for each inbox row:

  1. find the session (keyed by the HASHED user key: sessions.db never holds a
     phone number or PSID) and keep a SEALED reply address on it
  2. channel kill switch (P4): one static, approved reply -- never silence
  3. per-user rate limit (P4): every webhook arrives from Meta's IPs
  4. paused because a person took over (M4/H2): log only, don't reply
  5. stale after a Meta retry (W8): apologise + menu, never silently resume
  6. media (W5): nothing downloaded or stored; a safety reply
  7. a shared location (W6): the nearest branches
  8. everything else: the unchanged router pipeline, one bubble per turn
then the adapter renders (render.py) and sends.
"""

import math
import time

from .. import audit, config, router
from ..flows.locator import _load as load_branches
from ..identity import seal, user_hash
from ..messages import button, msg
from ..ratelimit import user_limiter
from ..session import store as default_store
from .base import InboundMessage

HUMAN = {"payload": "human_handoff"}
CHANNEL_OFF_REPEAT_SECONDS = 3600
NEAREST_COUNT = 3


def session_key(message: InboundMessage) -> str:
    return f"{message.channel}:{user_hash(message.session_key)}"


def _human_and_menu():
    return [button("talk_to_a_person", "human_handoff"), button("main_menu", "menu")]


def process(message: InboundMessage, findings, adapter, store=None):
    """Handle one inbound message end to end. Returns (replies, meta)."""
    store = store or default_store
    if message.kind == "comment":
        from .messenger import handle_comment

        return [], handle_comment(message)
    with store.session(session_key(message), message.channel) as (session, created):
        now = time.time()
        session.slots["reply_ref"] = seal(message.user_key)
        replies, meta = _respond(session, message, findings, created, now, adapter)
        if message.ts:
            session.last_inbound_at = max(session.last_inbound_at, message.ts)
        else:
            session.last_inbound_at = now
        if replies:
            adapter.send(message.user_key, replies, session=session)
        return replies, meta


def _inbound_text(message: InboundMessage) -> str:
    if message.text:
        return message.text  # already masked in the inbox
    if message.payload:
        return f"[button] {message.payload}"
    if message.location:
        return "[location shared]"  # coordinates are never logged
    if message.media_type:
        return f"[media: {message.media_type}]"
    return "[empty]"


def _respond(session, message, findings, created, now, adapter):
    # 2. Kill switch: a Meta channel can't be hidden, so "off" means one
    # static approved reply (at most hourly) pointing to a person.
    if not config.channel_enabled(message.channel):
        router.log_inbound(session, _inbound_text(message))
        last = session.slots.get("channel_off_sent", 0)
        if now - last < CHANNEL_OFF_REPEAT_SECONDS:
            return [], {"action": "channel_off_quiet"}
        session.slots["channel_off_sent"] = now
        return router.respond(session, [{"text": msg("channel_off"), "buttons": _human_and_menu()}],
                              {"action": "channel_off"})

    # 3. Per-user rate limit.
    if user_limiter.limited(session_key(message)):
        audit.log_event(session.id, "system", "rate limited", action="rate_limited",
                        channel=session.channel, user_hash=session.user_hash)
        return [], {"action": "rate_limited"}

    # 4. A person has taken over this conversation: log, don't answer.
    if session.bot_paused_until > now or message.kind == "standby":
        router.log_inbound(session, _inbound_text(message))
        audit.log_event(session.id, "system", "bot paused: a person has this conversation",
                        action="paused", channel=session.channel, user_hash=session.user_hash)
        return [], {"action": "paused"}

    adapter.mark_read(message)

    # 5. Stale: Meta retries for days after an outage. Apologise and offer the
    # menu; a days-old message must never be read as the answer to a question.
    if message.ts and now - message.ts > config.STALE_MESSAGE_MINUTES * 60:
        router.log_inbound(session, _inbound_text(message))
        session.greeted = True
        return router.respond(session, [{"text": msg("sorry_delay"), "buttons": list(router.MENU_BUTTONS)}],
                              {"action": "stale"})

    first = created or not session.greeted

    # 6. Media: nothing is downloaded or stored.
    if message.media_type and not message.text:
        router.log_inbound(session, _inbound_text(message))
        key = "voice_not_supported" if message.media_type in ("audio", "voice") else "media_not_accepted"
        replies = [{"text": msg(key), "buttons": _human_and_menu()}]
        if first:
            session.greeted = True
            replies.insert(0, {"text": msg("disclosure"), "buttons": []})
        return router.respond(session, replies, {"action": f"media:{message.media_type}"})

    # 7. A shared location: the nearest branches.
    if message.location:
        router.log_inbound(session, _inbound_text(message))
        replies = [nearest_branches_reply(*message.location)]
        if first:
            session.greeted = True
            replies.insert(0, {"text": msg("disclosure"), "buttons": []})
        return router.respond(session, replies, {"action": "nearest_branch"})

    # 8. The router, unchanged.
    if message.phone_hint:
        session.slots["phone_hint_ref"] = seal(message.phone_hint)
    return router.handle(session, text=message.text, payload=message.payload,
                         prior_findings=findings, first_contact=first)


# --- W6: nearest branch ----------------------------------------------------------

def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_branches(lat, lng, count=NEAREST_COUNT):
    branches = [b for b in load_branches()["branches"] if "lat" in b and "lng" in b]
    ranked = sorted(branches, key=lambda b: haversine_km(lat, lng, b["lat"], b["lng"]))
    return [(b, haversine_km(lat, lng, b["lat"], b["lng"])) for b in ranked[:count]]


def nearest_branches_reply(lat, lng) -> dict:
    lines = "\n".join(
        msg("locator.nearest_line", name=b["name"], address=b["address"], km=f"{km:.0f}",
            phone=b["phone"], hours=b["hours"])
        for b, km in nearest_branches(lat, lng)
    )
    return {
        "text": msg("locator.nearest", lines=lines),
        "buttons": [button("find_a_branch", "branch_locator"), button("talk_to_a_person", "human_handoff"),
                    button("main_menu", "menu")],
    }

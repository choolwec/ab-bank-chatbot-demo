"""The website channel: POST /chat for widget.js (ticket P2).

Moved out of main.py unchanged. The web is synchronous -- the reply goes back
in the HTTP response -- so it doesn't need the webhook inbox the Meta
channels use. The per-IP rate limiter applies here only (see ratelimit.py).
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import config, router
from ..ratelimit import client_ip, ip_limiter
from ..session import store

api = APIRouter()


class ChatIn(BaseModel):
    session_id: str | None = None
    # hard cap only; guards.clean() truncates to MAX_MESSAGE_CHARS
    message: str | None = Field(default=None, max_length=4000)
    payload: str | None = Field(default=None, max_length=100)


@api.post("/chat")
def chat(body: ChatIn, request: Request):
    if not config.widget_enabled():
        raise HTTPException(status_code=503, detail="Chat is currently unavailable.")
    if ip_limiter.limited(client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many messages — please slow down.")

    with store.web_session(body.session_id) as (session, created):
        if not body.message and not body.payload:
            # Empty post = the widget opening. A new session, or one idle past
            # IDLE_REGREET_MINUTES with nothing in progress, gets the welcome.
            # Otherwise it resumes: a page load must never wipe an in-progress
            # fraud/complaint/callback flow.
            fresh = created or not session.greeted or (session.returning and not session.active_flow)
            if fresh:
                replies = router.welcome(session)
                meta = {"action": "welcome"}
                history = []
            else:
                history = _history(session)
                replies, meta = router.resume(session)
            return {
                "session_id": session.id,
                "replies": replies,
                "meta": meta,
                "history": history,
            }
        replies, meta = router.handle(session, text=body.message, payload=body.payload)
        return {"session_id": session.id, "replies": replies, "meta": meta}


def _history(session) -> list[dict]:
    """Masked transcript for the widget to replay after a page reload.
    Button clicks are stored as '[button] <payload>' — internal ids, not
    something a customer should see — so they are skipped."""
    turns = [
        {"role": t["role"], "text": t["text"]}
        for t in session.transcript
        if not (t["role"] == "user" and t["text"].startswith("[button] "))
    ]
    return turns[-30:]

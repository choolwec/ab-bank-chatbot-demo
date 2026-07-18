"""FastAPI entrypoint (§3.2): POST /chat, GET /health, widget static files.

Input hygiene at the edge (§3.3): message length cap, per-IP rate limiting,
CORS locked to the bank's domain via ALLOWED_ORIGINS. HTTPS terminates at
IT's existing setup. No cookies — the widget holds a session id only.
"""

import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import audit, config, router
from .session import store

WIDGET_DIR = config.BASE_DIR / "widget"


@asynccontextmanager
async def lifespan(app):
    audit.init_db()
    audit.purge_expired()
    yield


app = FastAPI(title="AB Bank Zambia Assistant", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.mount("/widget", StaticFiles(directory=WIDGET_DIR), name="widget")


class ChatIn(BaseModel):
    session_id: str | None = None
    # hard cap only; guards.clean() truncates to MAX_MESSAGE_CHARS
    message: str | None = Field(default=None, max_length=4000)
    payload: str | None = Field(default=None, max_length=100)


_hits: dict[str, deque] = defaultdict(deque)


def _rate_limited(ip: str) -> bool:
    now = time.time()
    window = _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= config.RATE_LIMIT_PER_MINUTE:
        return True
    window.append(now)
    return False


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": app.version,
        "free_text_enabled": config.free_text_enabled(),
        "widget_enabled": config.widget_enabled(),
    }


@app.post("/chat")
def chat(body: ChatIn, request: Request):
    if not config.widget_enabled():
        raise HTTPException(status_code=503, detail="Chat is currently unavailable.")
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail="Too many messages — please slow down.")

    session, _created = store.get_or_create(body.session_id)
    if not body.message and not body.payload:
        replies = router.welcome(session)
        meta = {"action": "welcome"}
    else:
        replies, meta = router.handle(session, text=body.message, payload=body.payload)
    return {"session_id": session.id, "replies": replies, "meta": meta}


@app.get("/")
def demo_page():
    return FileResponse(WIDGET_DIR / "demo.html")

"""FastAPI entrypoint (§3.2): POST /chat, GET /health, widget static files.

Input hygiene at the edge (§3.3): message length cap, per-IP rate limiting,
CORS locked to the bank's domain via ALLOWED_ORIGINS. HTTPS terminates at
IT's existing setup. No cookies — the widget holds a session id only.
"""

import hmac
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import audit, config, jira_export, router
from .session import store

WIDGET_DIR = config.BASE_DIR / "widget"


@asynccontextmanager
async def lifespan(app):
    audit.init_db()
    audit.purge_expired()
    store.purge_expired()  # same retention schedule as the audit log (P1)
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


def _client_ip(request: Request) -> str:
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


def _rate_limited(ip: str) -> bool:
    now = time.time()
    if len(_hits) > 1024:  # shed buckets idle past the window (scanner churn)
        for key in [k for k, w in _hits.items() if not w or now - w[-1] > 60]:
            del _hits[key]
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
    if _rate_limited(_client_ip(request)):
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


@app.get("/")
def demo_page():
    return FileResponse(WIDGET_DIR / "demo.html")


_basic = HTTPBasic(auto_error=False)


def require_admin(credentials: HTTPBasicCredentials | None = Depends(_basic)) -> None:
    """Gate for every /admin/* route (P8). Unconfigured -> 404, so the route
    doesn't exist as far as the internet can tell; wrong or missing
    credentials -> 401 with a Basic challenge. Constant-time comparison."""
    expected = config.admin_credentials()
    if expected is None:
        raise HTTPException(status_code=404, detail="Not Found")
    ok = credentials is not None and (
        hmac.compare_digest(credentials.username.encode(), expected[0].encode())
        & hmac.compare_digest(credentials.password.encode(), expected[1].encode())
    )
    if not ok:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": 'Basic realm="admin"'},
        )


@app.get(
    "/admin/jira-preview",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
def jira_preview():
    """Staff-facing preview of the contact-center handoff — see CLAUDE.md
    for why this exists and jira_export.py for the mock/real split. It shows
    names, phone numbers and transcripts, hence require_admin."""
    return jira_export.render_jira_preview()

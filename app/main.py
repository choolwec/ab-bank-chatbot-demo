"""FastAPI entrypoint (§3.2): mounts the channels, /health, widget, admin.

Channels live in app/channels/ (ticket P2): the website's POST /chat is in
channels/web.py. Input hygiene at the edge (§3.3): message length cap, rate
limiting (ratelimit.py), CORS locked to the bank's domain via ALLOWED_ORIGINS.
HTTPS terminates at IT's existing setup. No cookies — the widget holds a
session id only.

Deployment: exactly ONE uvicorn worker/process. Sessions' per-key locks and
the rate-limit buckets live in process memory (see CLAUDE.md).
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import admin_cases, audit, config, jira_export
from .adminauth import require_admin
from .channels import messenger, web, whatsapp
from .desk import bridge
from .desk.links import links as desk_links
from .ratelimit import client_ip as _client_ip  # noqa: F401  (tests, docs)
from .ratelimit import ip_limiter
from .session import store
from .worker import worker

WIDGET_DIR = config.BASE_DIR / "widget"
_hits = ip_limiter.hits  # the per-IP buckets for /chat (tests clear them)


@asynccontextmanager
async def lifespan(app):
    audit.init_db()
    audit.purge_expired()
    store.purge_expired()  # same retention schedule as the audit log (P1)
    desk_links.purge(config.TRANSCRIPT_RETENTION_DAYS)  # H2; a no-op with the desk off
    worker.start()  # webhook channels: processes the durable inbox (W2)
    yield
    await worker.stop()


app = FastAPI(title="AB Bank Zambia Assistant", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.mount("/widget", StaticFiles(directory=WIDGET_DIR), name="widget")
app.include_router(web.api)
app.include_router(whatsapp.api)
app.include_router(messenger.api)
app.include_router(bridge.api)  # the agent desk's webhook (H2)
app.include_router(admin_cases.api)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": app.version,
        "free_text_enabled": config.free_text_enabled(),
        "widget_enabled": config.widget_enabled(),
    }


@app.get("/")
def demo_page():
    return FileResponse(WIDGET_DIR / "demo.html")


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

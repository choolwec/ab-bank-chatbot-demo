"""FastAPI entrypoint (§3.2): mounts the channels, /health, widget, admin.

Channels live in app/channels/ (ticket P2): the website's POST /chat is in
channels/web.py. Input hygiene at the edge (§3.3): message length cap, rate
limiting (ratelimit.py), CORS locked to the bank's domain via ALLOWED_ORIGINS.
HTTPS terminates at IT's existing setup. No cookies — the widget holds a
session id only.

Deployment: exactly ONE uvicorn worker/process. Sessions' per-key locks,
the rate-limit buckets and the /health counters (metrics.py) live in process
memory (see CLAUDE.md).
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import admin_cases, audit, config, jira_export, metrics
from . import health as health_checks
from . import inbox as inbox_mod
from .adminauth import require_admin
from .channels import messenger, web, whatsapp
from .housekeeping import housekeeper, purge_all
from .ratelimit import client_ip as _client_ip  # noqa: F401  (tests, docs)
from .ratelimit import ip_limiter
from .session import store
from .timing import TimingMiddleware, rss_mb, timings
from .worker import worker

WIDGET_DIR = config.BASE_DIR / "widget"
_hits = ip_limiter.hits  # the per-IP buckets for /chat (tests clear them)


@asynccontextmanager
async def lifespan(app):
    audit.init_db()
    purge_all()  # audit, sessions and the webhook inbox (R1); then nightly
    worker.start()  # webhook channels: processes the durable inbox (W2)
    housekeeper.start()
    yield
    await housekeeper.stop()
    await worker.stop()


app = FastAPI(title="AB Bank Zambia Assistant", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.add_middleware(metrics.WebhookStatusMiddleware)  # /health counts (R1)
app.add_middleware(TimingMiddleware)  # P9: server-side latency, /admin/timing
app.mount("/widget", StaticFiles(directory=WIDGET_DIR), name="widget")
app.include_router(web.api)
app.include_router(whatsapp.api)
app.include_router(messenger.api)
app.include_router(admin_cases.api)


@app.get("/health")
def health():
    """Uptime checkers read `checks.<name>.ok` (R1, health.py). A failing
    check keeps HTTP 200; only a check that cannot be computed at all (the
    app itself is broken) answers 503."""
    body = {
        "status": "ok",
        "version": app.version,
        "free_text_enabled": config.free_text_enabled(),
        "widget_enabled": config.widget_enabled(),
    }
    try:
        body["checks"] = health_checks.checks()
    except health_checks.ChecksBroken as broken:
        body.update(status="error", checks=broken.checks)
        return JSONResponse(body, status_code=503)
    return body


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


@app.get("/admin/timing", dependencies=[Depends(require_admin)])
def admin_timing():
    """P9: the server's own latency per route group and per worker message,
    the inbox queue, and memory -- what the load and soak test records."""
    from .ratelimit import ip_limiter, user_limiter

    return {
        "since": timings.since,
        "timings": timings.summary(),
        "inbox": {
            "oldest_pending_age_s": round(inbox_mod.inbox.oldest_pending_age(), 3),
            "counts": inbox_mod.inbox.counts(),
        },
        "process": {
            "rss_mb": rss_mb(),
            "session_locks": len(store._locks),
            "rate_limit_buckets": len(ip_limiter.hits) + len(user_limiter.hits),
        },
    }


@app.post("/admin/timing/reset", dependencies=[Depends(require_admin)])
def admin_timing_reset():
    timings.reset()
    return {"reset": True}

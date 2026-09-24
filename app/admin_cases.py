"""Staff follow-up on messaging-channel tickets (tickets W7, H1).

GET  /admin/cases                    open WhatsApp/Messenger tickets, with how to
                                     reply to each (inside or outside the 24-h window)
POST /admin/cases/{ref}/case-update  send the approved `case_update` template
                                     to the customer (WhatsApp)

Behind require_admin (P8). The form carries an HMAC token derived from the
admin password, so a page on another site can't make a logged-in browser
post it (Basic auth credentials are sent automatically). The customer's raw
WhatsApp id is only ever unsealed here, in memory, to send; it is never shown.
"""

import datetime as dt
import hashlib
import hmac
import html
import json
import sqlite3

import yaml
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from . import audit, config
from .adminauth import require_admin
from .identity import unseal

api = APIRouter(dependencies=[Depends(require_admin)])
TEMPLATES_FILE = config.KNOWLEDGE_DIR / "templates.yaml"


def load_templates() -> dict:
    return yaml.safe_load(TEMPLATES_FILE.read_text(encoding="utf-8"))["templates"]


def _csrf(ref: str) -> str:
    secret = (config.admin_credentials() or ("", ""))[1].encode()
    return hmac.new(secret, f"case_update:{ref}".encode(), hashlib.sha256).hexdigest()


def open_messaging_tickets() -> list[dict]:
    audit.init_db()
    con = sqlite3.connect(audit.DB_FILE)
    rows = con.execute(
        "SELECT ref, type, created, channel, reply_to FROM tickets"
        " WHERE status = 'open' AND channel IN ('whatsapp', 'messenger') ORDER BY created DESC LIMIT 200"
    ).fetchall()
    con.close()
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for ref, kind, created, channel, reply_to in rows:
        info = json.loads(reply_to) if reply_to else {}
        until = info.get("window_open_until")
        open_window = bool(until) and dt.datetime.fromisoformat(until) > now
        out.append({
            "ref": ref, "type": kind, "created": created, "channel": channel,
            "window_open": open_window, "window_open_until": until,
            "can_template": channel == "whatsapp" and bool(info.get("sealed")),
        })
    return out


@api.get("/admin/cases", response_class=HTMLResponse)
def cases_page():
    rows = []
    for t in open_messaging_tickets():
        how = ("Reply in the inbox (window open until " + html.escape(t["window_open_until"] or "") + ")"
               if t["window_open"] else "Window closed: send the case_update template")
        action = ""
        if t["can_template"] and not t["window_open"]:
            action = (
                f"<form method='post' action='/admin/cases/{html.escape(t['ref'])}/case-update'>"
                f"<input type='hidden' name='csrf' value='{_csrf(t['ref'])}'>"
                "<button type='submit'>Send case_update</button></form>"
            )
        rows.append(
            f"<tr><td>{html.escape(t['ref'])}</td><td>{html.escape(t['type'])}</td>"
            f"<td>{html.escape(t['channel'])}</td><td>{html.escape(t['created'])}</td>"
            f"<td>{how}</td><td>{action}</td></tr>"
        )
    body = "".join(rows) or "<tr><td colspan='6'>No open WhatsApp or Messenger tickets.</td></tr>"
    template = html.escape(load_templates()["case_update"]["body"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Case follow-up — AB Bank chatbot</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;color:#1a1a1a}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.4rem .6rem;text-align:left}}
th{{background:#f3f3f3}}.note{{background:#fff8e1;padding:.6rem 1rem;border-left:4px solid #f0b400}}</style>
</head><body><h1>Messaging-channel cases</h1>
<p class="note">Within 24 hours of the customer's last message you can reply freely in the inbox.
After that WhatsApp only allows the approved template: <em>{template}</em></p>
<table><tr><th>Reference</th><th>Type</th><th>Channel</th><th>Created</th><th>How to reply</th><th></th></tr>
{body}</table></body></html>"""


@api.post("/admin/cases/{ref}/case-update")
async def send_case_update(ref: str, request: Request):
    # A plain url-encoded form: parsed here rather than adding python-multipart.
    csrf = (parse_qs((await request.body()).decode("utf-8", "replace")).get("csrf") or [""])[0]
    if not hmac.compare_digest(csrf, _csrf(ref)):
        raise HTTPException(status_code=403, detail="forbidden")
    audit.init_db()
    con = sqlite3.connect(audit.DB_FILE)
    row = con.execute("SELECT channel, reply_to FROM tickets WHERE ref = ? AND status = 'open'", (ref,)).fetchone()
    con.close()
    if not row or row[0] != "whatsapp" or not row[1]:
        raise HTTPException(status_code=404, detail="no WhatsApp reply address for this case")
    info = json.loads(row[1])
    if not info.get("sealed"):
        raise HTTPException(status_code=404, detail="no WhatsApp reply address for this case")
    from .channels.whatsapp import sender

    ok = sender.send_template(unseal(info["sealed"]), "case_update", ref=ref)
    audit.log_event("-", "system", f"case_update template for {ref}: {'sent' if ok else 'failed'}",
                    action="template:case_update", channel="whatsapp", user_hash=info.get("user_hash"))
    if not ok:
        raise HTTPException(status_code=502, detail="send failed")
    return {"ref": ref, "sent": "case_update"}

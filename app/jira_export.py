"""Jira handoff (contact-center integration).

The contact center already runs on Jira and doesn't want a second queue to
watch, so a ticket doesn't just sit in our own SQLite — it also becomes a
Jira issue. Off by default (JIRA_ENABLED=false): no project/token exists
yet. Turning the flag on without credentials doesn't fail — it falls back
to MOCK mode, appending a "would-be" issue to data/jira_mock.jsonl and
served at GET /admin/jira-preview, so a demo can show exactly what staff
will see land in their queue with zero real Jira access.

Called from audit.create_ticket() as best-effort: a Jira outage or bad
credentials must never block the customer-facing ticket flow.

Operational alerts (R1, admin/alerts.py) use push_alert(): the same real/mock
switch and the same JIRA_ENABLED kill switch, label "chatbot-alert" (not
"chatbot", so a contact-centre filter on that label never picks them up), and
ALERT_JIRA_PROJECT_KEY when alerts belong in a different project.
"""

import datetime as dt
import json

import httpx

from . import config

_PRIORITY = {"fraud": "Highest", "complaint": "Medium", "callback": "Low", "handoff": "Medium"}
_LABELS = {
    "fraud": ["chatbot", "fraud"],
    "complaint": ["chatbot", "complaint"],
    "callback": ["chatbot", "callback"],
    "handoff": ["chatbot", "handoff"],
}
_TITLE = {"fraud": "Fraud / lost card report", "complaint": "Complaint", "callback": "Callback request",
          "handoff": "Conversation handed to a person"}

MOCK_FILE_NAME = "jira_mock.jsonl"

# R1: alert severity -> Jira priority.
ALERT_LABEL = "chatbot-alert"
ALERT_PRIORITY = {1: "Highest", 2: "High", 3: "Medium"}


def _summary(kind: str, ref: str, fields: dict) -> str:
    topic = fields.get("topic") or fields.get("what_happened") or _TITLE.get(kind, kind)
    return f"[Chatbot] {_TITLE.get(kind, kind.title())} {ref} — {topic}"[:250]


_REPLY_HOW = {
    "web": "Website visitor: call back on the number in the details (no chat channel to reply on).",
    "whatsapp": ("WhatsApp: reply in the agent inbox until {until}; after that WhatsApp only "
                 "allows the approved template 'case_update' (/admin/cases)."),
    "messenger": ("Messenger: reply in the Page Inbox until {until}; a person (not the bot) may "
                  "reply for up to 7 days with the HUMAN_AGENT tag, then only a template."),
}


def _description(ref: str, fields: dict, transcript: list, channel="web", reply_to=None) -> str:
    until = (reply_to or {}).get("window_open_until", "24 h after the customer's last message")
    lines = [f"Reference: {ref}", f"Channel: {channel}", "How to reply: " + _REPLY_HOW.get(
        channel, _REPLY_HOW["web"]).format(until=until), "", "Details:"]
    for k, v in fields.items():
        lines.append(f"- {k}: {v}")
    lines += ["", "Conversation transcript (PII already masked before storage):"]
    for turn in transcript[-40:]:
        lines.append(f"[{turn.get('role')}] {turn.get('text')}")
    return "\n".join(lines)


def push_ticket(kind: str, ref: str, fields: dict, transcript: list, channel="web", reply_to=None) -> dict | None:
    """Best-effort. Returns {"key","url","mode"} on success, or None if the
    integration is off entirely. A failed real push also returns None."""
    if not config.jira_enabled():
        return None

    summary = _summary(kind, ref, fields)
    description = _description(ref, fields, transcript, channel, reply_to)
    priority = _PRIORITY.get(kind, "Medium")
    labels = _LABELS.get(kind, ["chatbot"])

    if config.jira_configured():
        return _push_real(summary, description, priority, labels)
    return _push_mock(kind, ref, summary, description, priority, labels)


def push_alert(issue: str, severity: int, summary: str, description: str, transport=None) -> dict | None:
    """R1: one operational alert as a Jira issue. Same contract as
    push_ticket(): {"key","url","mode"}, or None when Jira is off or a real
    push failed. The caller (admin/alerts.py) passes counts and hints only."""
    if not config.jira_enabled():
        return None
    summary = summary[:250]
    priority = ALERT_PRIORITY.get(severity, "High")
    labels = [ALERT_LABEL, f"sev{severity}"]
    if config.jira_configured():
        return _push_real(summary, description, priority, labels,
                          project_key=config.alert_jira_project_key(), transport=transport)
    return _push_mock("alert", issue, summary, description, priority, labels)


def _push_real(summary, description, priority, labels, project_key=None, transport=None) -> dict | None:
    url = f"{config.JIRA_BASE_URL.rstrip('/')}/rest/api/2/issue"
    payload = {
        "fields": {
            "project": {"key": project_key or config.JIRA_PROJECT_KEY},
            "summary": summary,
            "description": description,
            "issuetype": {"name": "Task"},
            "priority": {"name": priority},
            "labels": labels,
        }
    }
    try:
        with httpx.Client(transport=transport, timeout=8.0) as client:  # tests inject a MockTransport
            resp = client.post(url, json=payload, auth=(config.JIRA_EMAIL, config.JIRA_API_TOKEN))
        resp.raise_for_status()
        key = resp.json().get("key")
        return {"key": key, "url": f"{config.JIRA_BASE_URL.rstrip('/')}/browse/{key}", "mode": "real"}
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def _push_mock(kind, ref, summary, description, priority, labels) -> dict:
    path = config.DATA_DIR / MOCK_FILE_NAME
    n = 1
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            n = sum(1 for _ in fh) + 1
    key = f"{config.JIRA_MOCK_PROJECT_KEY}-{n}"
    record = {
        "key": key,
        "kind": kind,
        "ref": ref,
        "summary": summary,
        "description": description,
        "priority": priority,
        "labels": labels,
        "status": "To Do",
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "mode": "mock",
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"key": key, "url": None, "mode": "mock"}


def read_mock_issues(limit: int = 100) -> list[dict]:
    path = config.DATA_DIR / MOCK_FILE_NAME
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return list(reversed(records))[:limit]


_PRIORITY_COLOR = {"Highest": "#DE350B", "High": "#FF5630", "Medium": "#FF991F", "Low": "#0065FF"}


def _escape(text) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _issue_card(issue: dict) -> str:
    color = _PRIORITY_COLOR.get(issue["priority"], "#6B778C")
    labels = "".join(
        f'<span class="label">{_escape(l)}</span>' for l in issue.get("labels", [])
    )
    return f"""
    <article class="card">
      <header>
        <span class="key">{_escape(issue['key'])}</span>
        <span class="priority" style="background:{color}">{_escape(issue['priority'])}</span>
        <span class="status">{_escape(issue['status'])}</span>
        <time>{_escape(issue['created'])}</time>
      </header>
      <h3>{_escape(issue['summary'])}</h3>
      <div class="labels">{labels}</div>
      <pre>{_escape(issue['description'])}</pre>
    </article>"""


def render_jira_preview() -> str:
    """A page that mimics what contact-center staff will see land in their
    real Jira project, generated from data/jira_mock.jsonl. Only ever
    populated when JIRA_ENABLED=true and no real Jira credentials are set —
    i.e. exactly the state this repo ships in for a demo."""
    issues = read_mock_issues()
    if not config.jira_enabled():
        banner = (
            "Jira handoff is currently OFF (JIRA_ENABLED=false). "
            "Turn it on in flags.json or via env var to see this preview populate."
        )
    elif config.jira_configured():
        banner = (
            "Jira is fully configured — real issues are being created in "
            f"{_escape(config.JIRA_BASE_URL)}, not shown here. This page only "
            "renders MOCK issues."
        )
    else:
        banner = (
            "MOCK MODE — no live Jira connection configured yet. This is a preview "
            "of exactly what will land in the contact center's real Jira project "
            "once IT supplies JIRA_BASE_URL / JIRA_PROJECT_KEY / JIRA_EMAIL / "
            "JIRA_API_TOKEN. Nothing on this page has left our own server."
        )
    cards = "".join(_issue_card(i) for i in issues) or "<p class='empty'>No tickets yet.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Jira preview — AB Bank chatbot handoff</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
          background: #F4F5F7; color: #172B4D; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0B1220; color: #DFE1E6; }}
    .card {{ background: #1B2436 !important; border-color: #2C3B54 !important; }}
    pre {{ background: #0B1220 !important; color: #B6C2CF !important; }}
    header.page {{ background: #0747A6 !important; }}
  }}
  header.page {{ background: #0052CC; color: #fff; padding: 16px 24px; }}
  header.page h1 {{ margin: 0; font-size: 18px; }}
  .banner {{ margin: 16px 24px; padding: 12px 16px; border-radius: 6px;
             background: #FFF0B3; color: #172B4D; font-size: 14px; }}
  main {{ padding: 8px 24px 40px; display: grid; gap: 14px; max-width: 900px; }}
  .card {{ background: #fff; border: 1px solid #DFE1E6; border-radius: 8px; padding: 14px 16px; }}
  .card header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 6px; font-size: 12px; }}
  .key {{ font-weight: 700; color: #0052CC; }}
  .priority {{ color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 11px; }}
  .status {{ background: #DFE1E6; padding: 2px 8px; border-radius: 3px; }}
  time {{ margin-left: auto; opacity: .7; }}
  .card h3 {{ margin: 4px 0 8px; font-size: 15px; }}
  .labels {{ margin-bottom: 8px; }}
  .label {{ display: inline-block; background: #EAE6FF; color: #403294; font-size: 11px;
            padding: 2px 8px; border-radius: 10px; margin-right: 6px; }}
  pre {{ white-space: pre-wrap; font-size: 12.5px; background: #FAFBFC; border-radius: 6px;
         padding: 10px; margin: 0; max-height: 260px; overflow: auto; }}
  .empty {{ padding: 24px; opacity: .7; }}
</style>
</head>
<body>
  <header class="page"><h1>Contact-center queue (Jira preview)</h1></header>
  <div class="banner">{banner}</div>
  <main>{cards}</main>
</body>
</html>"""

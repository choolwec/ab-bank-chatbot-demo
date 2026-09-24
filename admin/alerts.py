"""Operational alerts (ticket R1): run by cron every minute on the VM.

    python -m admin.alerts             check /health and send what is due
    python -m admin.alerts --dry-run   print what would be sent; send nothing,
                                       change no state
    python -m admin.alerts --test      post one test card to Teams, to check
                                       the Workflow URL (add --dry-run to print it)

It reads the RUNNING app's GET /health (ALERT_HEALTH_URL) rather than calling
the checks in-process: "/health down" is itself one of the alerts, and the
webhook and send counters live in the app's memory (app/metrics.py), so a
separate cron process computing the checks would always see zero. The
thresholds therefore live in one place, the app (config.py, applied by
app/health.py); this script maps each failing check to a severity, a message
and a first step (docs/runbook-incidents.md).

Where alerts go (decided by the PO):
  Teams  a Power Automate "Workflows" webhook that posts into the alerts group
         chat. ALERT_TEAMS_WEBHOOK_URL, environment only: anyone holding the
         URL can post into the chat. Unset: MOCK mode, appended to
         data/alerts_mock.jsonl (like Jira's mock mode).
  Jira   jira_export.push_alert(): real or mock exactly like tickets, behind
         the same JIRA_ENABLED kill switch.

Rate limits, per issue, kept in data/alerts_state.json:
  Teams  at most one post per ALERT_TEAMS_REPEAT_MINUTES (15) while the issue
         lasts, and one "resolved" post when it clears
  Jira   at most one issue per ALERT_JIRA_REPEAT_HOURS (24); people close it,
         the script never does
A rise in severity (failed messages that read as a fraud report) is sent at
once, whatever the limits. A send that fails is retried on the next run.

Silent unless a send failed (then a line on stderr and exit code 1), so cron's
MAILTO only ever mails a problem. Every payload carries check names, counts,
thresholds and hints: never an id, a user hash or message text.
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
from dataclasses import dataclass

import httpx

from app import config, hours, jira_export

STATE_FILE = "alerts_state.json"
MOCK_FILE = "alerts_mock.jsonl"
# A restart (a deploy) takes a few seconds: only an app that fails three
# tries, 10 s apart, counts as down.
HEALTH_TRIES = 3
HEALTH_RETRY_SECONDS = 10.0
RUNBOOK = "docs/runbook-incidents.md"

SEVERITY_MEANING = {
    1: "Sev 1: kill switch within 15 minutes, tell the PO and Compliance",
    2: "Sev 2: fix within 1 working day",
    3: "Sev 3: next content release",
}
# Adaptive Card colours: Attention is red, Warning amber, Good green.
_COLOUR = {1: "Attention", 2: "Warning", 3: "Accent"}


@dataclass
class Alert:
    issue: str
    severity: int
    title: str
    value: str
    threshold: str
    hint: str


# issue -> (severity, title, first step). Severities follow the R1 table in
# docs/execution-plan.md: nothing answering on any channel (fraud reports
# included) is Sev 1, and so is a broken flags.json, which silently undoes
# the kill switches that are the Sev 1 response; a degraded channel is Sev 2
# ("channel outage; webhook failures"). Sev 3 (a wrong-but-safe answer)
# comes from reviews, not a monitor.
ISSUES = {
    "health_down": (
        1, "The chatbot is not responding (/health down)",
        "Check the service on the VM (systemctl status abz-chatbot, then journalctl -u abz-chatbot -n 200) "
        "and restart it. Until it is back the website widget hides itself and WhatsApp and Messenger "
        "customers get no reply.",
    ),
    "worker_queue": (
        2, "Webhook messages are waiting too long",
        "The inbox worker is stuck or slow. Look for 'inbox processing failed' in the service log, then "
        "restart the service. Waiting messages are kept and answered in order after the restart.",
    ),
    "failed_messages": (
        2, "Customer messages failed after every retry",
        "These customers got no reply. Find the error in the service log (the inbox keeps it on each failed "
        "row) and fix the cause. If any was a fraud report this is Sev 1: tell the PO and the CC lead.",
    ),
    "send_failures": (
        2, "Replies to WhatsApp or Messenger are failing",
        "Check the service log for 'send failed' and Meta's status page. An HTTP 401 or 403 usually means an "
        "expired WA_ACCESS_TOKEN or MS_PAGE_TOKEN. If replies cannot be sent at all, switch that channel "
        "off (WHATSAPP_ENABLED or MESSENGER_ENABLED in flags.json).",
    ),
    "webhook_errors": (
        2, "Meta webhooks are getting server errors (5xx)",
        "Look for tracebacks in the service log. Meta retries failed deliveries, so fix and restart; if it "
        "persists, switch the channel off in flags.json.",
    ),
    "webhook_rejected": (
        2, "Signed Meta webhooks are being rejected",
        "Usually a wrong or rotated WA_APP_SECRET or MS_APP_SECRET in the environment file. Compare it with "
        "the Meta app dashboard and restart the service.",
    ),
    "flags_file": (
        1, "flags.json is broken: kill switches are back at their defaults",
        "Fix flags.json now: python -m json.tool flags.json shows a syntax error, and every value must be "
        "true or false without quotes. Until then every switch is at its default (free text, widget, "
        "WhatsApp and Messenger on; Jira off).",
    ),
    "embedding_model": (
        2, "The local model did not verify",
        "The second fraud check and the hybrid matcher are off; the keyword rules still work. Run "
        "python -m admin.fetch_model on the VM and restart the service.",
    ),
}
_UNKNOWN = (2, "A health check is failing", "Open /health and look at the failing check.")


# --- reading /health ----------------------------------------------------------------

def fetch_health(url=None, transport=None, tries=HEALTH_TRIES, wait=HEALTH_RETRY_SECONDS, sleep=time.sleep):
    """(health, None) when the app answers, else (None, what went wrong)."""
    url = url or config.ALERT_HEALTH_URL
    problem = ""
    for attempt in range(tries):
        try:
            with httpx.Client(transport=transport, timeout=10) as client:
                response = client.get(url)
            if response.status_code == 200:
                body = response.json()
                if isinstance(body, dict) and isinstance(body.get("checks"), dict):
                    return body, None
                problem = "the response has no checks"
            else:
                problem = f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            problem = f"no response ({type(exc).__name__})"
        except ValueError:
            problem = "the response is not JSON"
        if attempt < tries - 1:
            sleep(wait)
    return None, f"{problem} after {tries} tries"


# --- deciding -------------------------------------------------------------------------

def _pct(rate) -> str:
    return f"{float(rate) * 100:.1f}".rstrip("0").rstrip(".") + "%"


def _duration(seconds) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes} min {secs} s" if minutes else f"{secs} s"


def describe(name: str, check: dict) -> tuple[str, str]:
    """(value now, threshold) in words, from the check's counts."""
    try:
        if name == "worker_queue":
            return (f"oldest message waiting {_duration(check['oldest_pending_seconds'])}, "
                    f"{check['pending']} waiting", _duration(check["threshold_seconds"]))
        if name == "failed_messages":
            urgent = f", {check['urgent']} reading as a fraud report" if check.get("urgent") else ""
            return (f"{check['count']} in the last {check['window_minutes']} min{urgent}",
                    f"more than {check['threshold']}")
        if name == "send_failures":
            return (f"{_pct(check['rate'])} ({check['failed']} of {check['attempts']} sends "
                    f"in the last {check['window_minutes']} min)", f"more than {_pct(check['threshold'])}")
        if name == "webhook_errors":
            return (f"{_pct(check['rate'])} ({check['count_5xx']} of {check['requests']} requests "
                    f"in the last {check['window_minutes']} min)", f"more than {_pct(check['threshold'])}")
        if name == "webhook_rejected":
            return (f"{check['count']} in the last {check['window_minutes']} min",
                    f"more than {check['threshold']}")
        if name == "flags_file":
            if not check.get("readable", True):
                return "not valid JSON", "valid JSON with true/false values"
            return ("not true/false: " + ", ".join(check.get("invalid") or []),
                    "valid JSON with true/false values")
        if name == "embedding_model":
            needed = ", ".join(check.get("needed_by") or []) or "nothing"
            return ("verified" if check.get("verified") else f"not verified (needed by {needed})",
                    "verified")
    except (KeyError, TypeError, ValueError):
        pass
    return ("failing" if not check.get("ok", True) else "ok", "ok")


def evaluate(health: dict | None, problem: str | None = None) -> list[Alert]:
    """Every alert firing now. With /health down, that is the only one."""
    if health is None:
        severity, title, hint = ISSUES["health_down"]
        return [Alert("health_down", severity, title, problem or "no response", "HTTP 200 with checks", hint)]
    alerts = []
    for name, check in health.get("checks", {}).items():
        if not isinstance(check, dict) or check.get("ok", True):
            continue
        severity, title, hint = ISSUES.get(name, _UNKNOWN)
        if name == "failed_messages" and check.get("urgent"):
            severity = 1
        value, threshold = describe(name, check)
        alerts.append(Alert(name, severity, title, value, threshold, hint))
    return alerts


# --- Teams ----------------------------------------------------------------------------

def _when(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, hours.LUSAKA).strftime("%d/%m/%Y %H:%M") + " Lusaka"


def teams_payload(heading: str, colour: str, facts: list[tuple[str, str]], note: str) -> dict:
    """The body the Power Automate template "Post to a chat when a webhook
    request is received" expects: a message whose attachments are Adaptive
    Cards; the flow posts each attachment's `content` into the chat.
    [VERIFY] the exact schema against the flow the PO creates (the template's
    trigger reads `attachments`, and its "Post card" action renders Adaptive
    Cards up to a version Microsoft sets; 1.4 is the safe choice)."""
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": heading, "weight": "Bolder", "size": "Medium",
                     "color": colour, "wrap": True},
                    {"type": "FactSet", "facts": [{"title": t, "value": v} for t, v in facts]},
                    {"type": "TextBlock", "text": note, "wrap": True},
                ],
            },
        }],
    }


def firing_card(alert: Alert, since: float, env: str) -> dict:
    return teams_payload(
        f"Sev {alert.severity} · {alert.title}", _COLOUR.get(alert.severity, "Warning"),
        [("Severity", SEVERITY_MEANING.get(alert.severity, f"Sev {alert.severity}")),
         ("Now", alert.value), ("Threshold", alert.threshold), ("Since", _when(since)), ("Environment", env)],
        f"First step: {alert.hint} Runbook: {RUNBOOK}.",
    )


def resolved_card(title: str, value: str, threshold: str, since: float | None,
                  now: float, env: str) -> dict:
    lasted = _duration(now - since) if since else "unknown"
    return teams_payload(
        f"Resolved · {title}", "Good",
        [("Now", value), ("Threshold", threshold), ("Lasted", lasted), ("Environment", env)],
        "Back within its threshold. Any Jira issue raised for it stays open until a person closes it.",
    )


def ping_card(now: float, env: str) -> dict:
    return teams_payload(
        "Test · chatbot alerts reach this chat", "Accent",
        [("Environment", env), ("Sent", _when(now))],
        "Sent by python -m admin.alerts --test. No action needed.",
    )


def _warn(text: str) -> None:
    print(text, file=sys.stderr)


def send_teams(payload: dict, kind: str, issue: str, transport=None) -> bool:
    """POST to the Workflow, or append to data/alerts_mock.jsonl when no URL
    is set. Never prints the URL: it is a secret."""
    url = config.alert_teams_webhook_url()
    if not url:
        record = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "mode": "mock",
                  "kind": kind, "issue": issue, "payload": payload}
        with (config.DATA_DIR / MOCK_FILE).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    try:
        with httpx.Client(transport=transport, timeout=10) as client:
            response = client.post(url, json=payload)
    except httpx.HTTPError as exc:
        _warn(f"alerts: Teams post for {issue} failed ({type(exc).__name__})")
        return False
    if response.status_code >= 300:
        _warn(f"alerts: Teams post for {issue} failed (HTTP {response.status_code})")
        return False
    return True


# --- Jira -----------------------------------------------------------------------------

def jira_text(alert: Alert, since: float, env: str) -> tuple[str, str]:
    summary = f"[Chatbot alert] Sev {alert.severity}: {alert.title} ({env})"
    description = "\n".join([
        f"Severity: {SEVERITY_MEANING.get(alert.severity, alert.severity)}",
        f"Issue: {alert.title} ({alert.issue})",
        f"Now: {alert.value}",
        f"Threshold: {alert.threshold}",
        f"Since: {_when(since)}",
        f"Environment: {env}",
        "",
        f"First step: {alert.hint}",
        "",
        f"Runbook: {RUNBOOK}",
        "Opened automatically by admin/alerts.py, at most once per issue per "
        f"{config.ALERT_JIRA_REPEAT_HOURS} hours. Close it by hand once fixed (for Sev 1, once the "
        "post-mortem is written).",
    ])
    return summary, description


def send_jira(alert: Alert, since: float, env: str, transport=None) -> bool | None:
    """True when an issue was created, None when Jira is switched off,
    False when a real push failed (retried on the next run)."""
    if not config.jira_enabled():
        return None
    summary, description = jira_text(alert, since, env)
    result = jira_export.push_alert(alert.issue, alert.severity, summary, description, transport=transport)
    if result is None:
        _warn(f"alerts: Jira issue for {alert.issue} failed")
        return False
    return True


# --- state and the run ----------------------------------------------------------------

def load_state() -> dict:
    try:
        state = json.loads((config.DATA_DIR / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    if not isinstance(state.get("issues"), dict):
        state["issues"] = {}
    return state


def save_state(state: dict) -> None:
    path = config.DATA_DIR / STATE_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)  # atomic: a crash never leaves half a file


def run(now: float | None = None, dry_run: bool = False, health: dict | None = None,
        problem: str | None = None, fetch=None, transport=None, out=print) -> dict:
    """One pass. Returns what was (or, in a dry run, would be) sent."""
    now = time.time() if now is None else now
    if health is None and problem is None:
        health, problem = (fetch or fetch_health)()
    firing = {a.issue: a for a in evaluate(health, problem)}
    state = load_state()
    issues = state["issues"]
    env = config.alert_env_name()
    teams_every = config.ALERT_TEAMS_REPEAT_MINUTES * 60
    jira_every = config.ALERT_JIRA_REPEAT_HOURS * 3600
    report = {"firing": sorted(firing), "teams": [], "jira": [], "resolved": [], "failed": []}

    for name, alert in firing.items():
        st = issues.setdefault(name, {})
        since = st.get("since") or now
        teams_due = (now - st.get("teams_last", 0) >= teams_every
                     or alert.severity < st.get("teams_severity", alert.severity))
        jira_due = (now - st.get("jira_last", 0) >= jira_every
                    or alert.severity < st.get("jira_severity", alert.severity))
        if dry_run:
            if teams_due:
                out(f"[dry run] Teams, Sev {alert.severity} {name}:\n"
                    + json.dumps(firing_card(alert, since, env), indent=2, ensure_ascii=False))
                report["teams"].append(name)
            if jira_due and config.jira_enabled():
                summary, description = jira_text(alert, since, env)
                out(f"[dry run] Jira, {jira_export.ALERT_PRIORITY.get(alert.severity)}: {summary}\n{description}")
                report["jira"].append(name)
            continue
        st["since"] = since
        if teams_due:
            if send_teams(firing_card(alert, since, env), "firing", name, transport=transport):
                st.update(teams_last=now, teams_severity=alert.severity, notified=True)
                report["teams"].append(name)
            else:
                report["failed"].append(f"teams:{name}")
        if jira_due:
            sent = send_jira(alert, since, env, transport=transport)
            if sent:
                st.update(jira_last=now, jira_severity=alert.severity)
                report["jira"].append(name)
            elif sent is False:
                report["failed"].append(f"jira:{name}")

    # Clearing. With /health down the other checks are unknown, not resolved.
    for name, st in issues.items():
        if name in firing or not st.get("since"):
            continue
        if health is None and name != "health_down":
            continue
        if name == "health_down":
            title, value, threshold = ISSUES[name][1], "responding again", "HTTP 200 with checks"
        else:
            check = (health or {}).get("checks", {}).get(name)
            title = ISSUES.get(name, _UNKNOWN)[1]
            value, threshold = describe(name, check) if isinstance(check, dict) else ("no longer reported", "-")
        card = resolved_card(title, value, threshold, st.get("since"), now, env)
        if dry_run:
            if st.get("notified"):
                out(f"[dry run] Teams, resolved {name}:\n" + json.dumps(card, indent=2, ensure_ascii=False))
                report["resolved"].append(name)
            continue
        if st.get("notified"):
            if not send_teams(card, "resolved", name, transport=transport):
                report["failed"].append(f"teams:{name}:resolved")
                continue  # try the resolved post again next minute
            report["resolved"].append(name)
        st.update(since=None, notified=False)

    if dry_run:
        if not firing and not report["resolved"]:
            out("[dry run] All checks ok; nothing to send.")
    else:
        save_state(state)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check the chatbot's /health and send Teams/Jira alerts (R1).")
    parser.add_argument("--dry-run", action="store_true", help="print what would be sent; send nothing")
    parser.add_argument("--test", action="store_true", help="post one test card to Teams")
    args = parser.parse_args(argv)
    if args.test:
        payload = ping_card(time.time(), config.alert_env_name())
        if args.dry_run:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0
        if not send_teams(payload, "test", "test"):
            return 1
        where = "Teams" if config.alert_teams_webhook_url() else f"data/{MOCK_FILE} (ALERT_TEAMS_WEBHOOK_URL is not set)"
        print(f"Test card sent to {where}.")
        return 0
    report = run(dry_run=args.dry_run)
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())

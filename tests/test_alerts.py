"""R1: admin/alerts.py -- thresholds to alerts, the Teams Workflow payload,
Jira alerts (mock and a mocked real push), both rate limits, the resolved
post, and no PII or ids in anything sent. No real network anywhere."""

import copy
import json

import httpx
import pytest

from admin import alerts
from app import config, health, identity, inbox as inbox_mod, jira_export, metrics
from app.channels.base import InboundMessage

T0 = 1_790_000_000.0  # a fixed "now" for every run
TEAMS_URL = "https://prod.example.invalid/workflows/abc/triggers/manual/paths/invoke?sig=TOPSECRETSIG"


@pytest.fixture
def env(isolated_data, monkeypatch):
    """Mock Teams (no URL), mock Jira (enabled, no credentials), temp data/."""
    monkeypatch.delenv("ALERT_TEAMS_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("ALERT_JIRA_PROJECT_KEY", raising=False)
    monkeypatch.setenv("ALERT_ENV_NAME", "test-env")
    monkeypatch.setattr(config, "jira_enabled", lambda: True)
    monkeypatch.setattr(config, "jira_configured", lambda: False)
    return isolated_data


def healthy() -> dict:
    return {"status": "ok", "checks": {
        "worker_queue": {"ok": True, "oldest_pending_seconds": 0, "pending": 0, "threshold_seconds": 120},
        "failed_messages": {"ok": True, "count": 0, "urgent": 0, "threshold": 0, "window_minutes": 60},
        "send_failures": {"ok": True, "attempts": 10, "failed": 0, "rate": 0.0, "threshold": 0.02,
                          "window_minutes": 60, "by_channel": {}},
        "webhook_errors": {"ok": True, "requests": 10, "count_5xx": 0, "count_4xx": 0, "rate": 0.0,
                           "threshold": 0.01, "window_minutes": 60},
        "webhook_rejected": {"ok": True, "count": 0, "threshold": 2, "window_minutes": 60},
        "embedding_model": {"ok": True, "verified": True, "needed_by": ["URGENT_MODEL_ENABLED"]},
        "flags_file": {"ok": True, "readable": True, "invalid": []},
    }}


def failing(name, **fields) -> dict:
    body = copy.deepcopy(healthy())
    body["checks"][name].update(ok=False, **fields)
    return body


QUEUE_STUCK = dict(oldest_pending_seconds=312, pending=4)


def mock_lines(tmp, name):
    path = tmp / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def teams_posts(tmp, kind=None):
    return [r for r in mock_lines(tmp, alerts.MOCK_FILE) if kind is None or r["kind"] == kind]


def card_text(payload) -> str:
    return json.dumps(payload, ensure_ascii=False)


# --- thresholds -> alerts --------------------------------------------------------------

def test_the_real_health_shape_is_what_alerts_read(client, tmp_path, monkeypatch):
    """healthy() above mirrors the real /health, so the other tests stay honest."""
    monkeypatch.setattr(inbox_mod, "inbox", inbox_mod.Inbox(tmp_path / "inbox.db"))
    monkeypatch.setattr(health, "_model_verified", lambda needed: True)
    metrics.sends.clear()
    metrics.webhook_responses.clear()
    real = client.get("/health").json()["checks"]
    for name, check in healthy()["checks"].items():
        assert set(real[name]) == set(check), name
    assert alerts.evaluate({"checks": real}) == []


def test_all_healthy_fires_nothing():
    assert alerts.evaluate(healthy()) == []


def test_health_down_is_sev1():
    [alert] = alerts.evaluate(None, "HTTP 503 after 3 tries")
    assert (alert.issue, alert.severity) == ("health_down", 1)
    assert alert.value == "HTTP 503 after 3 tries"


@pytest.mark.parametrize("name, fields, severity, value_bit, threshold", [
    ("worker_queue", QUEUE_STUCK, 2, "5 min 12 s", "2 min 0 s"),
    ("failed_messages", dict(count=3), 2, "3 in the last 60 min", "more than 0"),
    ("send_failures", dict(attempts=40, failed=2, rate=0.05), 2, "5% (2 of 40", "more than 2%"),
    ("webhook_errors", dict(requests=200, count_5xx=3, rate=0.015), 2, "1.5% (3 of 200", "more than 1%"),
    ("webhook_rejected", dict(count=7), 2, "7 in the last 60 min", "more than 2"),
    ("embedding_model", dict(verified=False), 2, "not verified (needed by URGENT_MODEL_ENABLED)", "verified"),
    ("flags_file", dict(readable=False), 1, "not valid JSON", "valid JSON with true/false values"),
    ("flags_file", dict(invalid=["FREE_TEXT_ENABLED"]), 1, "not true/false: FREE_TEXT_ENABLED",
     "valid JSON with true/false values"),
])
def test_each_failing_check_maps_to_an_alert(name, fields, severity, value_bit, threshold):
    [alert] = alerts.evaluate(failing(name, **fields))
    assert (alert.issue, alert.severity) == (name, severity)
    assert value_bit in alert.value
    assert alert.threshold == threshold
    assert alert.hint


def test_failed_fraud_report_raises_to_sev1():
    [alert] = alerts.evaluate(failing("failed_messages", count=2, urgent=1))
    assert alert.severity == 1
    assert "1 reading as a fraud report" in alert.value


def test_an_unknown_failing_check_still_alerts():
    body = healthy()
    body["checks"]["something_new"] = {"ok": False}
    [alert] = alerts.evaluate(body)
    assert (alert.issue, alert.severity) == ("something_new", 2)


# --- reading /health --------------------------------------------------------------------

def test_fetch_health_retries_through_a_restart():
    replies = iter([httpx.ConnectError("refused"), httpx.ConnectError("refused"), healthy()])
    waits = []

    def handler(request):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return httpx.Response(200, json=reply)

    body, problem = alerts.fetch_health("http://app/health", transport=httpx.MockTransport(handler),
                                        sleep=waits.append)
    assert problem is None and body["checks"]
    assert waits == [alerts.HEALTH_RETRY_SECONDS] * 2


@pytest.mark.parametrize("reply, problem", [
    (httpx.Response(503, json={"status": "error"}), "HTTP 503 after 3 tries"),
    (httpx.Response(200, text="<html>proxy error</html>"), "the response is not JSON after 3 tries"),
    (httpx.Response(200, json={"status": "ok"}), "the response has no checks after 3 tries"),
])
def test_fetch_health_reports_down(reply, problem):
    transport = httpx.MockTransport(lambda request: reply)
    assert alerts.fetch_health("http://app/health", transport=transport, sleep=lambda s: None) == (None, problem)


def test_fetch_health_no_response():
    def refuse(request):
        raise httpx.ConnectError("refused")

    body, problem = alerts.fetch_health("http://app/health", transport=httpx.MockTransport(refuse),
                                        sleep=lambda s: None)
    assert body is None and problem == "no response (ConnectError) after 3 tries"


# --- the Teams payload ------------------------------------------------------------------

def test_teams_payload_is_a_workflow_adaptive_card():
    [alert] = alerts.evaluate(failing("worker_queue", **QUEUE_STUCK))
    payload = alerts.firing_card(alert, T0, "prod-vm")
    assert payload["type"] == "message"
    [attachment] = payload["attachments"]
    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
    card = attachment["content"]
    assert card["type"] == "AdaptiveCard" and card["version"] == "1.4"
    assert card["$schema"].startswith("http://adaptivecards.io/schemas/")
    heading, facts, note = card["body"]
    assert heading["type"] == "TextBlock" and heading["text"].startswith("Sev 2 · ")
    assert heading["color"] == "Warning"
    facts = {f["title"]: f["value"] for f in facts["facts"]}
    assert facts["Severity"].startswith("Sev 2")
    assert "5 min 12 s" in facts["Now"] and facts["Threshold"] == "2 min 0 s"
    assert facts["Environment"] == "prod-vm"
    assert facts["Since"].endswith("Lusaka") and facts["Since"][2] == "/"  # DD/MM/YYYY
    assert note["text"].startswith("First step: ") and "runbook-incidents.md" in note["text"]


def test_sev1_card_is_red():
    [alert] = alerts.evaluate(None, "no response")
    assert alerts.firing_card(alert, T0, "x")["attachments"][0]["content"]["body"][0]["color"] == "Attention"


def test_teams_mock_mode_without_a_url(env):
    report = alerts.run(now=T0, health=failing("worker_queue", **QUEUE_STUCK))
    assert report["teams"] == ["worker_queue"]
    [post] = teams_posts(env)
    assert post["mode"] == "mock" and post["kind"] == "firing" and post["issue"] == "worker_queue"
    assert post["payload"]["attachments"][0]["content"]["type"] == "AdaptiveCard"


def test_teams_real_post_goes_to_the_workflow_url(env, monkeypatch):
    monkeypatch.setenv("ALERT_TEAMS_WEBHOOK_URL", TEAMS_URL)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(202)  # what a Workflow trigger answers

    report = alerts.run(now=T0, health=failing("worker_queue", **QUEUE_STUCK),
                        transport=httpx.MockTransport(handler))
    assert report["teams"] == ["worker_queue"] and not report["failed"]
    [request] = seen
    assert str(request.url) == TEAMS_URL and request.method == "POST"
    assert json.loads(request.content)["type"] == "message"
    assert teams_posts(env) == []  # nothing in the mock file


def test_teams_failure_is_retried_and_never_prints_the_url(env, monkeypatch, capsys):
    monkeypatch.setenv("ALERT_TEAMS_WEBHOOK_URL", TEAMS_URL)

    def refuse(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")

    body = failing("worker_queue", **QUEUE_STUCK)
    report = alerts.run(now=T0, health=body, transport=httpx.MockTransport(refuse))
    assert report["failed"] == ["teams:worker_queue"]
    err = capsys.readouterr().err
    assert "Teams post for worker_queue failed (ConnectError)" in err
    assert "TOPSECRETSIG" not in err and "example.invalid" not in err
    assert "teams_last" not in alerts.load_state()["issues"]["worker_queue"]
    # a minute later it tries again, without waiting 15 minutes
    ok = httpx.MockTransport(lambda request: httpx.Response(202))
    assert alerts.run(now=T0 + 60, health=body, transport=ok)["teams"] == ["worker_queue"]


def test_teams_http_error_is_a_failure(env, monkeypatch, capsys):
    monkeypatch.setenv("ALERT_TEAMS_WEBHOOK_URL", TEAMS_URL)
    report = alerts.run(now=T0, health=failing("worker_queue", **QUEUE_STUCK),
                        transport=httpx.MockTransport(lambda request: httpx.Response(400)))
    assert report["failed"] == ["teams:worker_queue"]
    assert "HTTP 400" in capsys.readouterr().err


# --- Jira -----------------------------------------------------------------------------------

def test_jira_alert_in_mock_mode_renders_on_the_preview(env):
    alerts.run(now=T0, health=failing("worker_queue", **QUEUE_STUCK))
    [issue] = jira_export.read_mock_issues()
    assert issue["kind"] == "alert" and issue["ref"] == "worker_queue"
    assert issue["priority"] == "High"
    assert issue["labels"] == ["chatbot-alert", "sev2"]
    assert issue["summary"] == "[Chatbot alert] Sev 2: Webhook messages are waiting too long (test-env)"
    assert "Threshold: 2 min 0 s" in issue["description"] and "First step:" in issue["description"]
    page = jira_export.render_jira_preview()
    assert "Webhook messages are waiting too long" in page and "chatbot-alert" in page
    assert "#FF5630" in page  # High has its own colour


def test_sev1_jira_alert_is_highest(env):
    alerts.run(now=T0, health=None, problem="no response (ConnectError) after 3 tries")
    [issue] = jira_export.read_mock_issues()
    assert issue["priority"] == "Highest" and issue["labels"] == ["chatbot-alert", "sev1"]


def test_alerts_never_carry_the_contact_centre_label(env):
    alerts.run(now=T0, health=failing("send_failures", attempts=10, failed=5, rate=0.5))
    assert "chatbot" not in jira_export.read_mock_issues()[0]["labels"]


def test_jira_alert_real_push(env, monkeypatch):
    monkeypatch.setattr(config, "jira_configured", lambda: True)
    monkeypatch.setattr(config, "JIRA_BASE_URL", "https://jira.example.invalid/")
    monkeypatch.setattr(config, "JIRA_EMAIL", "bot@example.invalid")
    monkeypatch.setattr(config, "JIRA_API_TOKEN", "jira-token")
    monkeypatch.setattr(config, "JIRA_PROJECT_KEY", "CC")
    monkeypatch.setenv("ALERT_JIRA_PROJECT_KEY", "OPS")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(201, json={"key": "OPS-7"})

    report = alerts.run(now=T0, health=None, problem="HTTP 502 after 3 tries",
                        transport=httpx.MockTransport(handler))
    assert report["jira"] == ["health_down"] and not report["failed"]
    [request] = seen  # Teams stayed in mock mode
    assert str(request.url) == "https://jira.example.invalid/rest/api/2/issue"
    assert request.headers["authorization"].startswith("Basic ")
    fields = json.loads(request.content)["fields"]
    assert fields["project"] == {"key": "OPS"}  # alerts can live outside the CC project
    assert fields["priority"] == {"name": "Highest"}
    assert fields["labels"] == ["chatbot-alert", "sev1"]
    assert fields["summary"].startswith("[Chatbot alert] Sev 1: ")
    assert jira_export.read_mock_issues() == []


def test_jira_real_push_failure_is_retried_next_run(env, monkeypatch, capsys):
    monkeypatch.setattr(config, "jira_configured", lambda: True)
    monkeypatch.setattr(config, "JIRA_BASE_URL", "https://jira.example.invalid")
    body = failing("worker_queue", **QUEUE_STUCK)
    down = httpx.MockTransport(lambda request: httpx.Response(500))
    assert alerts.run(now=T0, health=body, transport=down)["failed"] == ["jira:worker_queue"]
    assert "Jira issue for worker_queue failed" in capsys.readouterr().err
    up = httpx.MockTransport(lambda request: httpx.Response(201, json={"key": "CC-1"}))
    assert alerts.run(now=T0 + 60, health=body, transport=up)["jira"] == ["worker_queue"]


def test_jira_switched_off_still_posts_to_teams(env, monkeypatch):
    monkeypatch.setattr(config, "jira_enabled", lambda: False)
    report = alerts.run(now=T0, health=failing("worker_queue", **QUEUE_STUCK))
    assert report["teams"] == ["worker_queue"] and report["jira"] == [] and not report["failed"]
    assert jira_export.read_mock_issues() == []


# --- rate limits, resolution, escalation -------------------------------------------------

def test_teams_at_most_once_per_15_minutes(env):
    body = failing("worker_queue", **QUEUE_STUCK)
    sent = [alerts.run(now=T0 + minute * 60, health=body)["teams"] for minute in range(0, 31)]
    assert [m for m, s in enumerate(sent) if s] == [0, 15, 30]
    assert len(teams_posts(env, "firing")) == 3


def test_jira_at_most_once_per_24_hours(env):
    body = failing("worker_queue", **QUEUE_STUCK)
    for offset in (0, 60, 15 * 60, 23 * 3600, 24 * 3600 - 1):
        alerts.run(now=T0 + offset, health=body)
    assert len(jira_export.read_mock_issues()) == 1
    alerts.run(now=T0 + 24 * 3600, health=body)
    assert len(jira_export.read_mock_issues()) == 2


def test_rate_limits_are_per_issue(env):
    alerts.run(now=T0, health=failing("worker_queue", **QUEUE_STUCK))
    body = failing("worker_queue", **QUEUE_STUCK)
    body["checks"]["webhook_rejected"].update(ok=False, count=9)
    report = alerts.run(now=T0 + 60, health=body)
    assert report["teams"] == ["webhook_rejected"] and report["jira"] == ["webhook_rejected"]


def test_rate_limits_survive_between_runs_in_the_state_file(env):
    alerts.run(now=T0, health=failing("worker_queue", **QUEUE_STUCK))
    state = json.loads((env / alerts.STATE_FILE).read_text(encoding="utf-8"))
    st = state["issues"]["worker_queue"]
    assert st["teams_last"] == T0 and st["jira_last"] == T0 and st["since"] == T0 and st["notified"]


def test_resolved_message_once_when_it_clears(env):
    alerts.run(now=T0, health=failing("worker_queue", **QUEUE_STUCK))
    report = alerts.run(now=T0 + 300, health=healthy())
    assert report["resolved"] == ["worker_queue"]
    [post] = teams_posts(env, "resolved")
    card = post["payload"]["attachments"][0]["content"]
    assert card["body"][0]["text"] == "Resolved · Webhook messages are waiting too long"
    assert card["body"][0]["color"] == "Good"
    facts = {f["title"]: f["value"] for f in card["body"][1]["facts"]}
    assert facts["Lasted"] == "5 min 0 s"
    assert alerts.run(now=T0 + 360, health=healthy())["resolved"] == []
    assert len(teams_posts(env, "resolved")) == 1
    assert len(jira_export.read_mock_issues()) == 1  # people close Jira issues, not the script


def test_failed_messages_resolved_card_does_not_claim_the_customers_were_answered(env):
    """The failed-row count clears when rows age out of the window, not when
    anyone replied to those customers: the card must say they still need it."""
    alerts.run(now=T0, health=failing("failed_messages", count=1))
    alerts.run(now=T0 + 3600, health=healthy())
    [post] = teams_posts(env, "resolved")
    note = post["payload"]["attachments"][0]["content"]["body"][2]["text"]
    assert "still had no reply" in note and "Back within its threshold" not in note


def test_a_new_episode_after_resolution_respects_the_15_minutes(env):
    body = failing("worker_queue", **QUEUE_STUCK)
    alerts.run(now=T0, health=body)
    alerts.run(now=T0 + 60, health=healthy())  # resolved
    assert alerts.run(now=T0 + 120, health=body)["teams"] == []  # flapping: no new post yet
    assert alerts.run(now=T0 + 180, health=healthy())["resolved"] == []  # nothing posted to resolve
    assert alerts.run(now=T0 + 16 * 60, health=body)["teams"] == ["worker_queue"]


def test_nothing_resolves_while_health_is_down(env):
    alerts.run(now=T0, health=failing("worker_queue", **QUEUE_STUCK))
    report = alerts.run(now=T0 + 60, health=None, problem="no response")
    assert report["firing"] == ["health_down"] and report["resolved"] == []
    report = alerts.run(now=T0 + 120, health=healthy())
    assert sorted(report["resolved"]) == ["health_down", "worker_queue"]


def test_health_down_resolution_says_it_is_back(env):
    alerts.run(now=T0, health=None, problem="no response")
    alerts.run(now=T0 + 120, health=healthy())
    [post] = teams_posts(env, "resolved")
    facts = {f["title"]: f["value"] for f in post["payload"]["attachments"][0]["content"]["body"][1]["facts"]}
    assert facts["Now"] == "responding again"


def test_escalation_to_sev1_bypasses_both_limits(env):
    alerts.run(now=T0, health=failing("failed_messages", count=1))
    report = alerts.run(now=T0 + 60, health=failing("failed_messages", count=2, urgent=1))
    assert report["teams"] == ["failed_messages"] and report["jira"] == ["failed_messages"]
    assert [i["priority"] for i in jira_export.read_mock_issues()] == ["Highest", "High"]
    # staying at Sev 1 goes back to the normal limits
    assert alerts.run(now=T0 + 120, health=failing("failed_messages", count=2, urgent=1))["teams"] == []


def test_dry_run_sends_nothing_and_keeps_no_state(env):
    printed = []
    report = alerts.run(now=T0, health=failing("worker_queue", **QUEUE_STUCK), dry_run=True, out=printed.append)
    assert report["teams"] == ["worker_queue"] and report["jira"] == ["worker_queue"]
    assert any('"AdaptiveCard"' in p for p in printed)
    assert any("[Chatbot alert] Sev 2" in p for p in printed)
    assert teams_posts(env) == [] and jira_export.read_mock_issues() == []
    assert not (env / alerts.STATE_FILE).exists()


def test_dry_run_when_all_is_well(env):
    printed = []
    alerts.run(now=T0, health=healthy(), dry_run=True, out=printed.append)
    assert printed == ["[dry run] All checks ok; nothing to send."]


def test_dry_run_says_when_everything_was_already_sent(env):
    body = failing("worker_queue", **QUEUE_STUCK)
    alerts.run(now=T0, health=body)
    printed = []
    alerts.run(now=T0 + 60, health=body, dry_run=True, out=printed.append)
    assert printed == ["[dry run] Firing: worker_queue; already sent within the rate limits."]


def test_a_quiet_run_prints_nothing(env, capsys):
    alerts.run(now=T0, health=failing("worker_queue", **QUEUE_STUCK))
    alerts.run(now=T0 + 60, health=healthy())
    assert capsys.readouterr() == ("", "")  # cron only mails when a send failed


# --- the command line --------------------------------------------------------------------

def test_main_test_card_in_mock_mode(env, capsys):
    assert alerts.main(["--test"]) == 0
    [post] = teams_posts(env, "test")
    assert post["payload"]["attachments"][0]["content"]["body"][0]["text"].startswith("Test · ")
    assert "ALERT_TEAMS_WEBHOOK_URL is not set" in capsys.readouterr().out


def test_main_test_card_dry_run_prints_it(env, capsys):
    assert alerts.main(["--test", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["type"] == "message"
    assert teams_posts(env) == []


def test_main_exit_code(env, monkeypatch):
    monkeypatch.setattr(alerts, "fetch_health", lambda: (failing("worker_queue", **QUEUE_STUCK), None))
    assert alerts.main([]) == 0
    monkeypatch.setattr(alerts, "send_teams", lambda *a, **k: False)  # a delivery fails
    monkeypatch.setattr(alerts, "fetch_health", lambda: (None, "no response"))
    assert alerts.main([]) == 1


# --- no PII, no ids ----------------------------------------------------------------------

def test_no_pii_or_ids_in_any_alert_payload(env, client, monkeypatch):
    """End to end: real failed rows full of personal data -> /health -> every
    alert channel. Nothing identifying may come out the other side."""
    raw_number, psid = "260977123456", "PSID-99887766"
    texts = ["I lost my card at Cairo Road, call me on 0977123456, NRC 123456/78/1",
             "someone stole K5000 from my account 4012888888881881"]
    box = inbox_mod.Inbox(env / "inbox.db")
    monkeypatch.setattr(inbox_mod, "inbox", box)
    monkeypatch.setattr(health, "_model_verified", lambda needed: False)
    metrics.sends.clear()
    metrics.webhook_responses.clear()
    for i, (text, user) in enumerate(zip(texts, (raw_number, psid))):
        box.store(InboundMessage(channel="whatsapp", user_key=user, text=text, msg_id=f"wamid.ID-{i}"))

    def explode(msg, findings):
        raise RuntimeError(f"failed for {msg.user_key}: {msg.text}")

    for _ in range(inbox_mod.MAX_ATTEMPTS):
        box.process_pending(explode)
    box.store(InboundMessage(channel="whatsapp", user_key=raw_number, text="hello", msg_id="wamid.ID-9"))
    metrics.record_send("whatsapp", False)
    metrics.webhook_responses.add("5xx")
    metrics.webhook_responses.add("signed_4xx", 5)

    seen = []
    monkeypatch.setenv("ALERT_TEAMS_WEBHOOK_URL", TEAMS_URL)
    body = client.get("/health").json()
    report = alerts.run(now=T0 + 10_000, health=body,
                        transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(202)))
    assert "failed_messages" in report["teams"] and len(report["jira"]) >= 4
    monkeypatch.delenv("ALERT_TEAMS_WEBHOOK_URL")
    alerts.run(now=T0 + 20_000, health=healthy())  # resolved cards, in the mock file

    sent = "\n".join(r.content.decode() for r in seen)
    sent += (env / alerts.MOCK_FILE).read_text(encoding="utf-8")
    sent += (env / jira_export.MOCK_FILE_NAME).read_text(encoding="utf-8")
    forbidden = [raw_number, "0977123456", psid, "99887766", "wamid", "ID-0", "Cairo", "lost my card",
                 "stole", "K5000", "4012", "123456/78", identity.user_hash(f"whatsapp:{raw_number}"),
                 identity.user_hash(f"whatsapp:{psid}"), "failed for"]
    assert not [f for f in forbidden if f in sent]


def test_failed_rows_keep_only_the_exception_type(env):
    """The error column is read by admins and survives until the retention
    purge: never the exception's message, which can quote the customer's
    text, a raw user id or a key."""
    import sqlite3

    box = inbox_mod.Inbox(env / "inbox.db")
    box.store(InboundMessage(channel="whatsapp", user_key="260977123456",
                             text="call me on 0977123456", msg_id="wamid.ERR-1"))

    def explode(msg, findings):
        raise ValueError(f"bad row for {msg.user_key}: {msg.text} token=EAAGsecret")

    box.process_pending(explode)  # a retry keeps the row 'new' with its error
    con = sqlite3.connect(env / "inbox.db")
    (status, error), = con.execute("SELECT status, error FROM inbound").fetchall()
    assert (status, error) == ("new", "ValueError")
    for _ in range(inbox_mod.MAX_ATTEMPTS):
        box.process_pending(explode)
    (status, error, failed_at), = con.execute("SELECT status, error, failed_at FROM inbound").fetchall()
    con.close()
    assert (status, error) == ("failed", "ValueError") and failed_at
    assert len(box.failed_since(3600)) == 1  # the R1 alert still counts it

"""Admin route auth gating (§ review of worldbank/data-ai-chatbot's
authorization-guardrails pattern): unset ADMIN_TOKEN keeps today's pre-launch
demo wide open; setting it requires a matching ?token= before this route,
which carries real customer name/phone/transcript data, is reachable."""

from app import config


def test_jira_preview_open_when_no_token_configured(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    response = client.get("/admin/jira-preview")
    assert response.status_code == 200


def test_jira_preview_rejects_missing_or_wrong_token(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret123")
    response = client.get("/admin/jira-preview")
    assert response.status_code == 403
    response = client.get("/admin/jira-preview", params={"token": "wrong"})
    assert response.status_code == 403


def test_jira_preview_accepts_correct_token(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret123")
    response = client.get("/admin/jira-preview", params={"token": "secret123"})
    assert response.status_code == 200

"""H4: the weekly "bot got this wrong" export, against a fake Chatwoot and a
fake Jira (httpx.MockTransport). No real network."""

import base64
import csv
import re
import time

import httpx
import pytest

from admin import export_bot_wrong
from admin.export_utterances import looks_personal
from app import config
from app.desk import chatwoot

NOW = time.time()
NOTE = """Handed over by the assistant on whatsapp. Case HND-20260924-AB12, Jira CC-9. The conversation so far:

[user] is there a fee for etumba transfers
[bot] I want to make sure I get this right, did you mean one of these?
[user] how do i send money to airtel from my account
[user] [button] human_handoff
[user] my number is [PHONE REDACTED]
[bot] I've passed our conversation to our team."""

JIRA_DESCRIPTION = """Reference: CMP-20260920-XY12
Channel: web
Details:
- topic: slow service

Conversation transcript (PII already masked before storage):
[user] can i change my branch
[bot] Here's what I'll send: ...
[user] call me on 0977123456
[user] how do i close my account"""


class FakeChatwoot:
    BASE = "/api/v1/accounts/1"

    def __init__(self):
        self.paths = []

    def handler(self, request):
        path = request.url.path[len(self.BASE):]
        self.paths.append(path)
        params = request.url.params
        if path == "/conversations":
            assert params["labels[]"] == "bot-wrong" and params["status"] == "all"
            if params["page"] != "1":
                return httpx.Response(200, json={"data": {"meta": {}, "payload": []}})
            return httpx.Response(200, json={"data": {"meta": {}, "payload": [
                {"id": 7, "labels": ["bot-wrong"], "last_activity_at": int(NOW - 3600)},
                {"id": 8, "labels": ["bot-wrong"], "last_activity_at": int(NOW - 10 * 86400)},  # too old
            ]}})
        m = re.fullmatch(r"/conversations/(\d+)/messages", path)
        if m:
            assert m.group(1) == "7", "an old conversation was fetched"
            if "before" in params:
                return httpx.Response(200, json={"meta": {}, "payload": []})
            return httpx.Response(200, json={"meta": {}, "payload": [
                {"id": 1, "message_type": 1, "private": True, "content": NOTE, "created_at": int(NOW - 7200)},
                {"id": 2, "message_type": 0, "private": False, "content": "Is there a fee for eTumba transfers",
                 "created_at": int(NOW - 7100)},
                {"id": 3, "message_type": 1, "private": False, "content": "Hello, this is Mary from AB Bank",
                 "created_at": int(NOW - 7000)},
                {"id": 4, "message_type": 0, "private": False, "content": "what documents do i need for a loan",
                 "created_at": int(NOW - 6900)},
            ]})
        return httpx.Response(404, json={})


class FakeJira:
    def __init__(self):
        self.requests = []

    def handler(self, request):
        self.requests.append(request)
        assert request.url.path == "/rest/api/2/search/jql"
        if request.url.params.get("nextPageToken") == "p2":
            return httpx.Response(200, json={"issues": [
                {"key": "CC-4", "fields": {"description": "[user] How do I close my account"}}], "isLast": True})
        return httpx.Response(200, json={"issues": [{"key": "CC-3", "fields": {"description": JIRA_DESCRIPTION}}],
                                         "nextPageToken": "p2", "isLast": False})


@pytest.fixture
def sources(monkeypatch, isolated_data):
    for var, value in {"CHATWOOT_URL": "https://desk.example.test", "CHATWOOT_ACCOUNT_ID": "1",
                       "CHATWOOT_INBOX_ID": "5", "CHATWOOT_API_TOKEN": "cw-token"}.items():
        monkeypatch.setenv(var, value)
    for name, value in {"JIRA_BASE_URL": "https://jira.example.test", "JIRA_EMAIL": "cc@example.test",
                        "JIRA_API_TOKEN": "jira-token", "JIRA_PROJECT_KEY": "CC"}.items():
        monkeypatch.setattr(config, name, value)
    desk, jira = FakeChatwoot(), FakeJira()
    client = chatwoot.ChatwootClient(transport=httpx.MockTransport(desk.handler), sleep=lambda s: None)
    return desk, jira, client


def _write_old_csv(path):
    """A CSV from before H4: no `source` column, one row already labelled."""
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["text", "predicted_intent", "score", "action", "label_a", "label_b"])
        writer.writerow(["is there a fee for eTumba transfers", "fees_etumba", "0.800", "answer", "fees_etumba", ""])


def _rows(path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_export_appends_customer_turns_from_chatwoot_and_jira(sources, tmp_path):
    desk, jira, client = sources
    out = tmp_path / "utterances.csv"
    _write_old_csv(out)
    result = export_bot_wrong.export(7, out, client=client, jira_transport=httpx.MockTransport(jira.handler))

    rows = _rows(out)
    assert list(rows[0]) == ["text", "predicted_intent", "score", "action", "label_a", "label_b", "source"]
    assert rows[0]["label_a"] == "fees_etumba" and rows[0]["source"] == ""  # kept as it was
    added = [r["text"] for r in rows if r["source"] == "bot-wrong"]
    assert added == [
        "how do i send money to airtel from my account",  # from the desk's transcript note
        "what documents do i need for a loan",             # sent to the agent
        "can i change my branch",                          # from the Jira description
        "how do i close my account",
    ]
    assert all(r["predicted_intent"] and r["label_a"] == "" for r in rows[1:])
    assert result == {"conversations": 1, "issues": 2, "added": 4, "errors": {}, "personal": 2, "duplicate": 3}

    text = out.read_text(encoding="utf-8")
    for leaked in ("0977123456", "REDACTED", "Mary", "[bot]", "I want to make sure", "human_handoff"):
        assert leaked not in text, leaked

    (first, second) = jira.requests
    jql = first.url.params["jql"]
    assert 'labels = "bot-wrong"' in jql and "updated >= -7d" in jql and 'project = "CC"' in jql
    assert first.headers["authorization"] == "Basic " + base64.b64encode(b"cc@example.test:jira-token").decode()
    assert second.url.params["nextPageToken"] == "p2"
    assert "/conversations/8/messages" not in desk.paths


def test_a_second_run_adds_nothing_new(sources, tmp_path):
    desk, jira, client = sources
    out = tmp_path / "utterances.csv"
    first = export_bot_wrong.export(7, out, client=client, jira_transport=httpx.MockTransport(jira.handler))
    again = export_bot_wrong.export(7, out, client=client, jira_transport=httpx.MockTransport(jira.handler))
    assert first["added"] == 5 and again["added"] == 0 and len(_rows(out)) == 5


def test_one_source_failing_keeps_the_other(sources, tmp_path):
    desk, jira, client = sources
    out = tmp_path / "utterances.csv"
    result = export_bot_wrong.export(7, out, client=client,
                                     jira_transport=httpx.MockTransport(lambda r: httpx.Response(401, json={})))
    assert result["errors"] == {"jira": "HTTP 401"} and result["added"] == 3  # the desk's rows
    assert {r["source"] for r in _rows(out)} == {"bot-wrong"}


def test_nothing_is_fetched_when_neither_source_is_configured(monkeypatch, isolated_data, tmp_path):
    def refuse(request):
        raise AssertionError(f"network call: {request.url}")

    monkeypatch.delenv("CHATWOOT_URL", raising=False)
    monkeypatch.setattr(config, "JIRA_BASE_URL", "")
    client = chatwoot.ChatwootClient(transport=httpx.MockTransport(refuse))
    out = tmp_path / "utterances.csv"
    result = export_bot_wrong.export(7, out, client=client, jira_transport=httpx.MockTransport(refuse))
    assert result["added"] == 0 and not out.exists()


def test_the_second_pii_check_also_catches_the_desk_phone_mask():
    assert looks_personal("my number is [PHONE REDACTED]")
    assert not looks_personal("how do i close my account")


def test_export_utterances_marks_its_rows_as_audit(bot):
    from admin.export_utterances import export

    bot().say("what is etumba")
    (row,) = export(days=1)
    assert row["source"] == "audit"

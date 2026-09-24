"""R1: the /health `checks` object -- counts only, `ok` per check, HTTP 200
unless the app itself is broken."""

import json
import sqlite3
import time

import httpx
import pytest

from app import embedder, health, identity, inbox as inbox_mod, metrics, urgent_model
from app.channels import whatsapp
from app.channels.base import InboundMessage

RAW_NUMBER = "260977123456"
SECRET_TEXT = "I lost my card at Cairo Road, call me on 0977123456"


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A temp inbox seen by the checks only: the running app's worker keeps
    its own reference, so it never processes these rows."""
    b = inbox_mod.Inbox(tmp_path / "inbox.db")
    monkeypatch.setattr(inbox_mod, "inbox", b)
    metrics.webhook_responses.clear()
    metrics.sends.clear()
    monkeypatch.setattr(health, "_model_verified", lambda needed: True)
    yield b
    metrics.webhook_responses.clear()
    metrics.sends.clear()


def _store(b, text=SECRET_TEXT, msg_id="wamid.SECRET-1", user=RAW_NUMBER):
    assert b.store(InboundMessage(channel="whatsapp", user_key=user, text=text, msg_id=msg_id))
    return f"whatsapp:{msg_id}"


def _fail_everything(b):
    def handler(msg, findings):
        raise RuntimeError("downstream exploded")

    for _ in range(inbox_mod.MAX_ATTEMPTS):
        b.process_pending(handler)


def test_existing_fields_unchanged_and_all_checks_ok(client, box):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["widget_enabled"] is True
    assert body["free_text_enabled"] is True
    assert set(body["checks"]) == set(health.CHECKS)
    assert all(check["ok"] is True for check in body["checks"].values())


def test_stale_queue_fails_its_check_but_stays_200(client, box):
    row = _store(box)
    with sqlite3.connect(box.path) as con:
        con.execute("UPDATE inbound SET received = ? WHERE id = ?", (time.time() - 300, row))
    response = client.get("/health")
    assert response.status_code == 200
    check = response.json()["checks"]["worker_queue"]
    assert check["ok"] is False
    assert check["oldest_pending_seconds"] >= 299
    assert check["pending"] == 1
    assert check["threshold_seconds"] == 120


def test_fresh_queue_is_ok(box):
    _store(box)
    assert health.worker_queue()["ok"] is True


def test_failed_rows_fail_their_check_and_fraud_is_counted_as_urgent(client, box):
    _store(box)  # "I lost my card": a fraud report
    _store(box, text="what are your opening hours", msg_id="wamid.SECRET-2")
    _fail_everything(box)
    check = client.get("/health").json()["checks"]["failed_messages"]
    assert check == {"ok": False, "count": 2, "urgent": 1, "threshold": 0, "window_minutes": 60}


def test_failed_rows_leave_the_window_after_an_hour(box):
    _store(box)
    _fail_everything(box)
    with sqlite3.connect(box.path) as con:
        con.execute("UPDATE inbound SET failed_at = ?", (time.time() - 3700,))
    assert health.failed_messages()["count"] == 0


def test_old_inbox_gains_failed_at_in_place(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as con:  # the W2 schema, before R1
        con.execute(
            "CREATE TABLE inbound (id TEXT PRIMARY KEY, channel TEXT NOT NULL, user_hash TEXT NOT NULL,"
            " user_ref TEXT, received REAL NOT NULL, ts REAL, message TEXT NOT NULL, findings TEXT,"
            " status TEXT NOT NULL DEFAULT 'new', attempts INTEGER NOT NULL DEFAULT 0, error TEXT)"
        )
    b = inbox_mod.Inbox(path)
    with sqlite3.connect(path) as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(inbound)")}
    assert "failed_at" in columns
    _store(b)
    _fail_everything(b)
    assert len(b.failed_since(60)) == 1


def test_send_failures_over_threshold(client, box):
    for _ in range(48):
        metrics.record_send("whatsapp", True)
    metrics.record_send("whatsapp", False)
    metrics.record_send("messenger", True)
    check = client.get("/health").json()["checks"]["send_failures"]
    assert check["attempts"] == 50 and check["failed"] == 1
    assert check["rate"] == 0.02 and check["ok"] is True  # exactly at 2%: not over
    metrics.record_send("messenger", False)
    check = client.get("/health").json()["checks"]["send_failures"]
    assert check["ok"] is False
    assert check["by_channel"] == {"whatsapp": {"ok": 48, "failed": 1}, "messenger": {"ok": 1, "failed": 1}}


def test_a_real_failed_send_is_counted(box, isolated_data, monkeypatch):
    monkeypatch.setenv("WA_ACCESS_TOKEN", "token")
    monkeypatch.setenv("WA_PHONE_NUMBER_ID", "PHONE_ID")
    transport = httpx.MockTransport(lambda request: httpx.Response(400, json={"error": {}}))
    sender = whatsapp.WhatsAppSender(transport=transport, sleep=lambda s: None)
    assert not sender.send(RAW_NUMBER, [{"text": "hi", "buttons": [{"label": "A", "payload": "a"}]}])
    ok = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    assert whatsapp.WhatsAppSender(transport=ok).send(RAW_NUMBER, [{"text": "hi", "buttons": []}])
    assert metrics.sends.counts() == {"whatsapp:failed": 1, "whatsapp:ok": 1}
    assert health.send_failures()["ok"] is False


def test_mock_sends_are_not_counted(box, isolated_data, monkeypatch):
    monkeypatch.delenv("WA_ACCESS_TOKEN", raising=False)
    whatsapp.WhatsAppSender().send(RAW_NUMBER, [{"text": "hi", "buttons": []}])
    assert metrics.sends.counts() == {}


def test_webhook_5xx_rate(box):
    metrics.webhook_responses.add("2xx", 99)
    metrics.webhook_responses.add("5xx", 1)
    assert health.webhook_errors()["ok"] is True  # 1%: not over
    metrics.webhook_responses.add("5xx", 1)
    check = health.webhook_errors()
    assert check["ok"] is False
    assert check["requests"] == 101 and check["count_5xx"] == 2


def test_signed_rejections(box):
    metrics.webhook_responses.add("signed_4xx", 2)
    assert health.webhook_rejected()["ok"] is True
    metrics.webhook_responses.add("signed_4xx")
    assert health.webhook_rejected()["ok"] is False


def test_embedding_model_only_fails_when_something_needs_it(monkeypatch):
    monkeypatch.setattr(embedder, "available", lambda: False)
    monkeypatch.setattr(embedder, "verify", lambda model_dir=None: False)
    monkeypatch.setattr(health, "_verified_once", None)
    monkeypatch.setattr(urgent_model, "enabled", lambda: True)
    check = health.embedding_model()
    assert check == {"ok": False, "verified": False, "needed_by": ["URGENT_MODEL_ENABLED"]}
    monkeypatch.setattr(urgent_model, "enabled", lambda: False)
    monkeypatch.setenv("EMBEDDINGS_ENABLED", "false")
    monkeypatch.setenv("SHADOW_MATCHER", "false")
    assert health.embedding_model() == {"ok": True, "verified": False, "needed_by": []}


def test_embedding_model_verified(monkeypatch):
    monkeypatch.setattr(embedder, "available", lambda: True)
    monkeypatch.setattr(urgent_model, "enabled", lambda: True)
    assert health.embedding_model()["ok"] is True


class BrokenInbox:
    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise sqlite3.OperationalError("disk I/O error at /secret/path")

        return fail


def test_unreadable_store_is_503_without_the_error_text(client, box, monkeypatch):
    monkeypatch.setattr(inbox_mod, "inbox", BrokenInbox())
    response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["widget_enabled"] is True  # existing fields still there
    assert body["checks"]["worker_queue"] == {"ok": False, "error": "unavailable"}
    assert body["checks"]["send_failures"]["ok"] is True  # the others still computed
    assert "secret" not in response.text


def test_health_carries_counts_only(client, box):
    _store(box)
    _store(box, text="someone stole money from my account", msg_id="wamid.SECRET-2", user="PSID-99887766")
    _fail_everything(box)
    _store(box, msg_id="wamid.SECRET-3")  # pending
    metrics.record_send("whatsapp", False)
    text = client.get("/health").text
    forbidden = [RAW_NUMBER, "0977123456", "PSID-99887766", "wamid", "SECRET", "Cairo", "lost my card",
                 "stole", "exploded", identity.user_hash(f"whatsapp:{RAW_NUMBER}")]
    assert not [f for f in forbidden if f in text]
    checks = json.loads(text)["checks"]
    assert checks["failed_messages"]["count"] == 2 and checks["failed_messages"]["urgent"] == 2
    assert checks["worker_queue"]["pending"] == 1

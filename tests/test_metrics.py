"""R1: the in-memory rolling counters and the /webhooks/* status middleware."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import metrics


@pytest.fixture(autouse=True)
def _fresh_counters():
    metrics.webhook_responses.clear()
    metrics.sends.clear()
    yield
    metrics.webhook_responses.clear()
    metrics.sends.clear()


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def test_rolling_counter_keeps_one_hour():
    clock = Clock(1_000_020.0)
    counter = metrics.RollingCounter(window=3600, clock=clock)
    counter.add("5xx")
    counter.add("2xx", 3)
    assert counter.counts() == {"5xx": 1, "2xx": 3}
    clock.t += 59 * 60  # still inside the hour
    counter.add("2xx")
    assert counter.counts() == {"5xx": 1, "2xx": 4}
    clock.t += 60  # the first minute has left the window
    assert counter.counts() == {"2xx": 1}
    clock.t += 3600
    assert counter.counts() == {}


def test_rolling_counter_memory_is_bounded():
    clock = Clock(0.0)
    counter = metrics.RollingCounter(window=3600, clock=clock)
    for minute in range(500):
        clock.t = minute * 60.0
        counter.add("2xx")
    assert len(counter._buckets) <= 60
    assert counter.counts() == {"2xx": 60}


def test_record_send_counts_by_channel_and_outcome():
    metrics.record_send("whatsapp", True)
    metrics.record_send("whatsapp", False)
    metrics.record_send("messenger", True)
    assert metrics.sends.counts() == {"whatsapp:ok": 1, "whatsapp:failed": 1, "messenger:ok": 1}


def _mini_app():
    mini = FastAPI()
    mini.add_middleware(metrics.WebhookStatusMiddleware)

    @mini.post("/webhooks/ok")
    def ok():
        return {"ok": True}

    @mini.post("/webhooks/bad")
    def bad():
        raise HTTPException(status_code=401, detail="bad signature")

    @mini.post("/webhooks/boom")
    def boom():
        raise RuntimeError("unexpected")

    @mini.get("/elsewhere")
    def elsewhere():
        raise HTTPException(status_code=500)

    return mini


def test_middleware_counts_webhook_responses_by_class():
    with TestClient(_mini_app(), raise_server_exceptions=False) as c:
        assert c.post("/webhooks/ok").status_code == 200
        assert c.post("/webhooks/ok").status_code == 200
        assert c.post("/webhooks/bad").status_code == 401
        assert c.post("/webhooks/boom").status_code == 500  # an escaped exception
        assert c.get("/elsewhere").status_code == 500  # not a webhook: not counted
    assert metrics.webhook_responses.counts() == {"2xx": 2, "4xx": 1, "5xx": 1}


def test_middleware_reraises_what_it_counts():
    with TestClient(_mini_app()) as c, pytest.raises(RuntimeError):
        c.post("/webhooks/boom")
    assert metrics.webhook_responses.counts() == {"5xx": 1}


def test_signed_4xx_only_when_meta_signature_header_present():
    with TestClient(_mini_app()) as c:
        c.post("/webhooks/bad")  # an unsigned probe
        c.post("/webhooks/bad", headers={"X-Hub-Signature-256": "sha256=00"})
        c.post("/webhooks/ok", headers={"X-Hub-Signature-256": "sha256=00"})
    counts = metrics.webhook_responses.counts()
    assert counts["4xx"] == 2
    assert counts["signed_4xx"] == 1


def test_real_webhooks_are_counted(client, monkeypatch):
    monkeypatch.setenv("WA_APP_SECRET", "real-secret")
    client.post("/webhooks/whatsapp", content=b"{}")  # no signature at all
    client.post("/webhooks/messenger", content=b"{}", headers={"X-Hub-Signature-256": "sha256=wrong"})
    client.get("/health")  # never counted
    counts = metrics.webhook_responses.counts()
    assert counts.get("4xx") == 2
    assert counts.get("signed_4xx") == 1
    assert "2xx" not in counts

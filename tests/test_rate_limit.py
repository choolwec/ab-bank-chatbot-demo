"""Proxy-aware rate limiting: X-Forwarded-For is only trusted when
PROXY_HOPS says our own infrastructure appended it (see app/main._client_ip).
"""

import json

import pytest

from app import audit, config
from app import main as app_main
from app.ratelimit import ip_limiter


@pytest.fixture(autouse=True)
def _fresh_limiter():
    app_main._hits.clear()
    ip_limiter.reported.clear()
    yield
    app_main._hits.clear()
    ip_limiter.reported.clear()


def _post(client, xff=None):
    headers = {"X-Forwarded-For": xff} if xff else {}
    return client.post("/chat", json={}, headers=headers)


def test_xff_ignored_without_proxy_hops(client, monkeypatch):
    monkeypatch.delenv("PROXY_HOPS", raising=False)
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MINUTE", 3)
    # A client can't dodge the limiter by rotating a spoofed header.
    for i in range(3):
        assert _post(client, f"203.0.113.{i}").status_code == 200
    assert _post(client, "203.0.113.99").status_code == 429


def test_xff_used_behind_proxy(client, monkeypatch):
    monkeypatch.setenv("PROXY_HOPS", "1")
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MINUTE", 3)
    for _ in range(3):
        assert _post(client, "198.51.100.7").status_code == 200
    # Same real client is limited...
    assert _post(client, "198.51.100.7").status_code == 429
    # ...but another visitor behind the same proxy is not.
    assert _post(client, "198.51.100.8").status_code == 200


def test_client_supplied_xff_prefix_is_ignored(client, monkeypatch):
    monkeypatch.setenv("PROXY_HOPS", "1")
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MINUTE", 3)
    # With one trusted hop, only the RIGHTMOST entry (proxy-appended) counts;
    # a rotating attacker-supplied prefix must not create fresh buckets.
    for i in range(3):
        assert _post(client, f"10.0.0.{i}, 198.51.100.7").status_code == 200
    assert _post(client, "10.0.0.99, 198.51.100.7").status_code == 429


def test_web_refusals_are_logged_once_a_minute_per_visitor(client, monkeypatch, isolated_data):
    # Concern #10: the weekly report's "Rate limited" line read 0 for the web.
    monkeypatch.setenv("PROXY_HOPS", "1")
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MINUTE", 2)
    for ip in ("198.51.100.7", "198.51.100.8"):
        for _ in range(2):
            assert _post(client, ip).status_code == 200
        for _ in range(5):  # a flood writes one event, not five
            assert _post(client, ip).status_code == 429
    rows = [r for r in map(json.loads, audit.JSONL_FILE.read_text(encoding="utf-8").splitlines())
            if r["action"] == "rate_limited"]
    assert len(rows) == 2
    assert all(r["channel"] == "web" and r["session_id"] == "-" and r["user_hash"] is None for r in rows)
    assert "198.51.100" not in audit.JSONL_FILE.read_text(encoding="utf-8")  # the IP is never logged


def test_first_refusal_reports_again_after_the_window(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("app.ratelimit.time.time", lambda: clock[0])
    assert ip_limiter.first_refusal("k") is True
    assert ip_limiter.first_refusal("k") is False
    clock[0] += ip_limiter.window + 1
    assert ip_limiter.first_refusal("k") is True

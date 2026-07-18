"""Proxy-aware rate limiting: X-Forwarded-For is only trusted when
PROXY_HOPS says our own infrastructure appended it (see app/main._client_ip).
"""

import pytest

from app import config
from app import main as app_main


@pytest.fixture(autouse=True)
def _fresh_limiter():
    app_main._hits.clear()
    yield
    app_main._hits.clear()


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

import os

# Raise the per-IP rate limit before the app imports config — the whole test
# suite arrives from one client IP.
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "100000")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def chat(client, session_id=None, message=None, payload=None):
    body = {"session_id": session_id}
    if message is not None:
        body["message"] = message
    if payload is not None:
        body["payload"] = payload
    response = client.post("/chat", json=body)
    assert response.status_code == 200, response.text
    return response.json()


class Bot:
    """Drives router.handle() in-process for one conversation (no HTTP)."""

    def __init__(self, channel="web"):
        import uuid

        from app import router
        from app.session import SessionStore

        self.router = router
        if channel == "web":
            self.session, _ = SessionStore().get_or_create()
        else:
            store = SessionStore()
            self.session, _ = store._open(f"{channel}:test-{uuid.uuid4().hex}", channel)[1:]
        self.router.welcome(self.session)
        self.last = None

    def say(self, text):
        self.last = self.router.handle(self.session, text=text)
        return self.last

    def tap(self, payload):
        self.last = self.router.handle(self.session, payload=payload)
        return self.last

    @property
    def action(self):
        return self.last[1].get("action")

    @property
    def text(self):
        return " ".join(r["text"] for r in self.last[0])

    @property
    def buttons(self):
        return [b["payload"] for b in self.last[0][-1]["buttons"]]


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Point the audit trail and Jira mock log at a temp dir."""
    from app import audit, config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(audit, "DB_FILE", tmp_path / "audit.db")
    monkeypatch.setattr(audit, "JSONL_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr(audit, "_init_done", False)
    return tmp_path


@pytest.fixture
def bot(isolated_data):
    """A factory: bot() returns a fresh in-process conversation."""
    return Bot

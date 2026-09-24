import os

# Raise the per-IP rate limit before the app imports config — the whole test
# suite arrives from one client IP.
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "100000")
# H5: the CSAT sample depends on each session's random user_hash, so it is
# OFF for the suite unless a test turns it on (monkeypatch.setenv) -- no test
# may get an extra feedback reply by chance.
os.environ["CSAT_SAMPLE_RATE"] = "0"

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


class MetaEnv:
    """Helpers for the WhatsApp / Messenger webhook tests (isolated data)."""

    APP_SECRET = "test-app-secret"
    VERIFY_TOKEN = "test-verify-token"

    def __init__(self, tmp_path, client):
        self.tmp = tmp_path
        self.client = client

    def sign(self, raw: bytes) -> str:
        import hashlib
        import hmac

        return "sha256=" + hmac.new(self.APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()

    def post(self, channel, body, signature=None):
        import json

        raw = json.dumps(body).encode() if not isinstance(body, bytes) else body
        headers = {"Content-Type": "application/json"}
        headers["X-Hub-Signature-256"] = signature if signature is not None else self.sign(raw)
        return self.client.post(f"/webhooks/{channel}", content=raw, headers=headers)

    def process(self):
        from app import worker

        return worker.process_now()

    def outbox(self, channel):
        import json

        path = self.tmp / f"{channel}_outbox_mock.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def sent_texts(self, channel):
        """The customer-visible text of every mock send (not read receipts)."""
        out = []
        for m in self.outbox(channel):
            if channel == "whatsapp":
                if m.get("type") == "text":
                    out.append(m["text"]["body"])
                elif m.get("type") == "interactive":
                    out.append(m["interactive"]["body"]["text"])
            elif "message" in m:
                out.append(m["message"].get("text", ""))
        return out


@pytest.fixture
def meta_env(tmp_path, monkeypatch, client, isolated_data):
    from app import inbox as inbox_mod
    from app import worker as worker_mod
    from app.channels import messaging, messenger, whatsapp
    from app.ratelimit import user_limiter
    from app.session import SqliteSessionStore

    box = inbox_mod.Inbox(tmp_path / "inbox.db")
    store = SqliteSessionStore(tmp_path / "sessions.db")
    for mod in (inbox_mod, worker_mod, whatsapp, messenger):
        monkeypatch.setattr(mod, "inbox", box)
    monkeypatch.setattr(messaging, "default_store", store)
    monkeypatch.setattr("app.session.store", store)
    for var in ("WA_ACCESS_TOKEN", "WA_PHONE_NUMBER_ID", "MS_PAGE_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("WA_APP_SECRET", MetaEnv.APP_SECRET)
    monkeypatch.setenv("WA_VERIFY_TOKEN", MetaEnv.VERIFY_TOKEN)
    monkeypatch.setenv("MS_APP_SECRET", MetaEnv.APP_SECRET)
    monkeypatch.setenv("MS_VERIFY_TOKEN", MetaEnv.VERIFY_TOKEN)
    monkeypatch.setenv("MS_APP_ID", "OUR_APP")
    monkeypatch.setenv("MS_PAGE_ID", "PAGE_ID")
    user_limiter.hits.clear()
    env = MetaEnv(tmp_path, client)
    env.inbox, env.store = box, store
    yield env
    user_limiter.hits.clear()


@pytest.fixture(autouse=True)
def _office_hours(monkeypatch):
    """Every test runs at a fixed in-hours moment (Wednesday 10:00 Lusaka),
    so no test depends on when the suite runs (H3). Out-of-hours tests set
    their own time."""
    import datetime as dt

    from app import hours

    fixed = dt.datetime(2026, 9, 23, 10, 0, tzinfo=hours.LUSAKA)
    monkeypatch.setattr(hours, "now", lambda: fixed)
    return fixed

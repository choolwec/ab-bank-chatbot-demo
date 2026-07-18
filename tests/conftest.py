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

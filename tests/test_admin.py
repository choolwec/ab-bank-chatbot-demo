"""P8: every /admin/* route is behind HTTP Basic auth, and off by default."""

import pytest

from app.main import app

ADMIN_ROUTES = sorted(
    r.path for r in app.routes if getattr(r, "path", "").startswith("/admin")
)


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("ADMIN_USER", "cc-lead")
    monkeypatch.setenv("ADMIN_PASSWORD", "correct horse")
    return ("cc-lead", "correct horse")


def test_there_are_admin_routes_to_protect():
    assert "/admin/jira-preview" in ADMIN_ROUTES


@pytest.mark.parametrize("path", ADMIN_ROUTES)
def test_admin_route_is_404_when_not_configured(client, monkeypatch, path):
    monkeypatch.delenv("ADMIN_USER", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ADMIN_ROUTES)
def test_admin_route_is_401_without_credentials(client, creds, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")


@pytest.mark.parametrize("path", ADMIN_ROUTES)
def test_admin_route_is_401_with_wrong_credentials(client, creds, path):
    assert client.get(path, auth=("cc-lead", "wrong")).status_code == 401
    assert client.get(path, auth=("someone", creds[1])).status_code == 401


@pytest.mark.parametrize("path", ADMIN_ROUTES)
def test_admin_route_is_200_with_credentials(client, creds, path):
    assert client.get(path, auth=creds).status_code == 200


def test_half_configured_counts_as_off(client, monkeypatch):
    monkeypatch.setenv("ADMIN_USER", "cc-lead")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert client.get("/admin/jira-preview").status_code == 404

"""P8: every /admin/* route is behind HTTP Basic auth, and off by default."""

import pytest

from app.main import app

def _all_routes(routes):
    """Every route, including those inside included routers (newer FastAPI
    keeps an included router as one lazy entry in app.routes)."""
    for r in routes:
        inner = getattr(r, "original_router", None)
        if inner is not None:
            yield from _all_routes(inner.routes)
        else:
            yield r


ROUTES = list(_all_routes(app.routes))
# GET routes are probed with GET; POST-only ones with POST.
ADMIN_ROUTES = sorted(
    (r.path, "GET" if "GET" in (getattr(r, "methods", None) or ()) else "POST")
    for r in ROUTES if getattr(r, "path", "").startswith("/admin")
)


def _call(client, route, **kwargs):
    path, method = route
    path = path.replace("{ref}", "FRD-00000000-TEST")
    return client.request(method, path, **kwargs)


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("ADMIN_USER", "cc-lead")
    monkeypatch.setenv("ADMIN_PASSWORD", "correct horse")
    return ("cc-lead", "correct horse")


def test_there_are_admin_routes_to_protect():
    paths = {p for p, _ in ADMIN_ROUTES}
    assert {"/admin/jira-preview", "/admin/cases", "/admin/cases/{ref}/case-update"} <= paths


@pytest.mark.parametrize("route", ADMIN_ROUTES)
def test_admin_route_is_404_when_not_configured(client, monkeypatch, route):
    monkeypatch.delenv("ADMIN_USER", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert _call(client, route).status_code == 404


@pytest.mark.parametrize("route", ADMIN_ROUTES)
def test_admin_route_is_401_without_credentials(client, creds, route):
    response = _call(client, route)
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")


@pytest.mark.parametrize("route", ADMIN_ROUTES)
def test_admin_route_is_401_with_wrong_credentials(client, creds, route):
    assert _call(client, route, auth=("cc-lead", "wrong")).status_code == 401
    assert _call(client, route, auth=("someone", creds[1])).status_code == 401


@pytest.mark.parametrize("route", [r for r in ADMIN_ROUTES if r[1] == "GET"])
def test_admin_route_is_200_with_credentials(client, creds, route):
    assert _call(client, route, auth=creds).status_code == 200


def test_case_update_needs_the_page_token_even_with_credentials(client, creds):
    """Basic auth is sent automatically by the browser, so a form on another
    site must not be able to post this: the HMAC page token is required."""
    r = client.post("/admin/cases/FRD-00000000-TEST/case-update", auth=creds, content=b"csrf=forged",
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 403


def test_half_configured_counts_as_off(client, monkeypatch):
    monkeypatch.setenv("ADMIN_USER", "cc-lead")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert client.get("/admin/jira-preview").status_code == 404

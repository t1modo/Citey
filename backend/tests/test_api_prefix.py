"""Every backend route lives under /api; old root paths redirect there."""

from fastapi.testclient import TestClient

from citey.config import Settings, get_settings
from citey.services.email_service import make_confirm_email_url
from citey.main import create_app


def _client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        cron_secret="s3cret", app_url="https://www.citey.email"
    )
    return TestClient(app, follow_redirects=False)


def test_routes_are_served_under_api() -> None:
    client = _client()
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/openapi.json").status_code == 200
    assert client.get("/api/docs").status_code == 200
    # Unauthenticated, but routed: the handler answers, not a 404.
    assert client.get("/api/profile").status_code == 401


def test_root_still_answers_for_host_health_checks() -> None:
    assert _client().get("/").json() == {"status": "ok"}


def test_old_paths_redirect_keeping_method_and_query() -> None:
    client = _client()
    resp = client.get("/profile/confirm-notification-email?uid=u1&token=t")
    assert resp.status_code == 308
    assert resp.headers["location"] == "/api/profile/confirm-notification-email?uid=u1&token=t"

    resp = client.post("/jobs/run", json={"dry_run": True})
    assert resp.status_code == 308
    assert resp.headers["location"] == "/api/jobs/run"


def test_preflight_on_an_old_path_is_answered_by_cors_not_redirected() -> None:
    app = create_app()
    resp = TestClient(app, follow_redirects=False).options(
        "/profile",
        headers={
            "Origin": "https://www.citey.email",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


def test_confirmation_links_point_at_the_api_route() -> None:
    url = make_confirm_email_url(
        "u1", "a@b.c", "https://www.citey.email/", Settings(cron_secret="x")
    )
    assert url.startswith("https://www.citey.email/api/profile/confirm-notification-email?")

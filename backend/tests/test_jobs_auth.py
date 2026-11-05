"""Authorization rules for the /jobs endpoints."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from main import app


def _settings(**overrides) -> Settings:
    base = {"cron_secret": "s3cret", "app_url": "https://citey.email"}
    base.update(overrides)
    return Settings(**base)


def _client(**overrides) -> TestClient:
    app.dependency_overrides[get_settings] = lambda: _settings(**overrides)
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_orphan_cleanup_rejects_signed_in_users() -> None:
    client = _client()
    with patch("app.routers.jobs.verify_token", return_value={"uid": "user1"}), \
         patch("app.services.citation_service.cleanup_orphan_users", new=AsyncMock()) as job:
        resp = client.post(
            "/jobs/cleanup-orphan-users",
            json={"dry_run": True},
            headers={"Authorization": "Bearer token"},
        )
    assert resp.status_code == 403
    job.assert_not_awaited()


def test_orphan_cleanup_accepts_cron_secret() -> None:
    client = _client()
    with patch("app.firebase_client.get_db"), patch(
        "app.services.citation_service.cleanup_orphan_users",
        new=AsyncMock(return_value={"deleted": 0}),
    ) as job:
        resp = client.post(
            "/jobs/cleanup-orphan-users",
            json={"dry_run": True},
            headers={"X-Cron-Secret": "s3cret"},
        )
    assert resp.status_code == 200
    job.assert_awaited_once()


def test_wrong_cron_secret_is_forbidden() -> None:
    client = _client()
    resp = client.post(
        "/jobs/cleanup-orphan-users",
        json={"dry_run": True},
        headers={"X-Cron-Secret": "nope"},
    )
    assert resp.status_code == 403


def test_default_cron_secret_refused_in_production() -> None:
    client = _client(cron_secret="changeme")
    resp = client.post(
        "/jobs/cleanup-orphan-users",
        json={"dry_run": True},
        headers={"X-Cron-Secret": "changeme"},
    )
    assert resp.status_code == 503

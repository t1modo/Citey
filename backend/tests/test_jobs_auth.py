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
            "/api/jobs/cleanup-orphan-users",
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
            "/api/jobs/cleanup-orphan-users",
            json={"dry_run": True},
            headers={"X-Cron-Secret": "s3cret"},
        )
    assert resp.status_code == 200
    job.assert_awaited_once()


def test_wrong_cron_secret_is_forbidden() -> None:
    client = _client()
    resp = client.post(
        "/api/jobs/cleanup-orphan-users",
        json={"dry_run": True},
        headers={"X-Cron-Secret": "nope"},
    )
    assert resp.status_code == 403


def test_default_cron_secret_refused_in_production() -> None:
    client = _client(cron_secret="changeme")
    resp = client.post(
        "/api/jobs/cleanup-orphan-users",
        json={"dry_run": True},
        headers={"X-Cron-Secret": "changeme"},
    )
    assert resp.status_code == 503


def test_cron_run_executes_job_off_the_event_loop() -> None:
    import threading

    seen: dict = {}

    async def fake_job(**kwargs):
        # asyncio.to_thread workers are named "asyncio_N"; the request
        # handler itself never runs on one of those.
        seen["thread"] = threading.current_thread().name.startswith("asyncio_")
        return {"users_processed": 0, "works_processed": 0, "new_notifications": 0}

    client = _client()
    with patch("app.firebase_client.get_db"), patch(
        "app.services.citation_service.run_job_for_all_users", new=fake_job
    ):
        resp = client.post("/api/jobs/run", json={"dry_run": True}, headers={"X-Cron-Secret": "s3cret"})
    assert resp.status_code == 200
    assert seen["thread"] is True


def test_overlapping_cron_runs_are_refused() -> None:
    import threading

    started, release = threading.Event(), threading.Event()

    async def slow_job(**kwargs):
        started.set()
        release.wait(5)
        return {"users_processed": 0, "works_processed": 0, "new_notifications": 0}

    client = _client()
    results: dict = {}
    with patch("app.firebase_client.get_db"), patch(
        "app.services.citation_service.run_job_for_all_users", new=slow_job
    ):
        def first():
            results["first"] = client.post(
                "/api/jobs/run", json={"dry_run": True}, headers={"X-Cron-Secret": "s3cret"}
            ).status_code

        t = threading.Thread(target=first)
        t.start()
        assert started.wait(5)
        second = client.post("/api/jobs/run", json={"dry_run": True}, headers={"X-Cron-Secret": "s3cret"})
        release.set()
        t.join(5)

    assert second.status_code == 409
    assert results["first"] == 200

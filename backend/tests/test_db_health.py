"""The Neon database health check, over async psycopg."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


def _async_conn(fetches: list) -> tuple[MagicMock, AsyncMock]:
    """A fake psycopg.AsyncConnection whose cursor returns *fetches* in order."""
    cur = AsyncMock()
    cur.fetchone.side_effect = fetches
    conn = MagicMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)
    conn.cursor.return_value.__aenter__ = AsyncMock(return_value=cur)
    conn.cursor.return_value.__aexit__ = AsyncMock(return_value=False)
    conn.transaction.return_value.__aenter__ = AsyncMock()
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
    return conn, cur


def test_db_health_reports_not_configured_without_database_url():
    with patch("app.core.db.get_settings") as settings:
        settings.return_value.database_url = ""
        resp = TestClient(app).get("/api/health/db")
    assert resp.status_code == 503
    assert resp.json() == {"status": "not_configured"}


def test_db_health_runs_write_and_read_in_a_rolled_back_transaction():
    conn, cur = _async_conn([("neondb", "17.5"), ("ok",), (1,)])
    with patch("app.core.db.get_settings") as settings, patch(
        "app.core.db.psycopg.AsyncConnection.connect", new=AsyncMock(return_value=conn)
    ) as connect:
        settings.return_value.database_url = "postgresql://u:p@host/neondb"
        resp = TestClient(app).get("/api/health/db")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok" and body["write_read_ok"] is True and body["database"] == "neondb"
    assert connect.call_args.kwargs["prepare_threshold"] is None  # pooler: no prepared statements
    conn.transaction.assert_called_once_with(force_rollback=True)
    assert cur.execute.await_count == 4


def test_db_health_hides_connection_errors():
    with patch("app.core.db.get_settings") as settings, patch(
        "app.core.db.psycopg.AsyncConnection.connect",
        new=AsyncMock(side_effect=RuntimeError("could not connect to ep-secret-host")),
    ):
        settings.return_value.database_url = "postgresql://u:p@host/neondb"
        resp = TestClient(app).get("/api/health/db")
    assert resp.status_code == 503
    assert "ep-secret-host" not in resp.text

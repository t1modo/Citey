"""The Neon database health check."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from citey.main import app


def test_db_health_reports_not_configured_without_database_url():
    with patch("citey.db.get_settings") as settings:
        settings.return_value.database_url = ""
        resp = TestClient(app).get("/api/health/db")
    assert resp.status_code == 503
    assert resp.json() == {"status": "not_configured"}


def test_db_health_runs_write_and_read_in_a_rolled_back_transaction():
    cur = MagicMock()
    cur.fetchone.side_effect = [("neondb", "17.5"), ("ok",), (1,)]
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    with patch("citey.db.get_settings") as settings, patch("citey.db.psycopg.connect") as connect:
        settings.return_value.database_url = "postgresql://u:p@host/neondb"
        connect.return_value.__enter__.return_value = conn
        resp = TestClient(app).get("/api/health/db")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok" and body["write_read_ok"] is True and body["database"] == "neondb"
    assert connect.call_args.kwargs["prepare_threshold"] is None  # pooler: no prepared statements
    conn.transaction.assert_called_once_with(force_rollback=True)


def test_db_health_hides_connection_errors():
    with patch("citey.db.get_settings") as settings, patch(
        "citey.db.psycopg.connect", side_effect=RuntimeError("could not connect to ep-secret-host")
    ):
        settings.return_value.database_url = "postgresql://u:p@host/neondb"
        resp = TestClient(app).get("/api/health/db")
    assert resp.status_code == 503
    assert "ep-secret-host" not in resp.text

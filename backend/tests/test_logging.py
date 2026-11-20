"""
error_logs rows with correlation ids, no secrets, JSON fallback (Joyal); AI, RAG and weather log rows (Piyush).

Owner: Joyal (M1) + Piyush (M2), see 'Shared files'  |  Spec: Agile Spec v2.0 > Testing strategy
"""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.deps import get_db
from app.main import app
from app.repositories import log_repo


def error_rows(test_engine) -> list[dict]:
    with test_engine.connect() as db:
        return [dict(row) for row in db.execute(text("SELECT * FROM error_logs ORDER BY error_id")).mappings()]


# --- Joyal/M1: error_logs, JSON fallback, no secrets ---
class TestErrorLogs:
    """[J] Joyal: every 4xx/5xx writes an error_logs row (US-04)."""

    @pytest.fixture(autouse=True)
    def _empty_error_logs(self, test_engine):
        with test_engine.begin() as db:
            db.execute(text("TRUNCATE error_logs RESTART IDENTITY"))
        yield

    def test_failed_call_stores_row_with_ids(self, api_client, team, auth_header, test_engine) -> None:
        response = api_client.get(
            "/api/v1/trips/999999", headers={**auth_header(team["employee"]), "X-Correlation-ID": "corr-trip-404"}
        )
        assert response.status_code == 404
        rows = error_rows(test_engine)
        assert len(rows) == 1
        row = rows[0]
        assert (row["error_code"], row["http_status"], row["category"], row["severity"]) == (
            "NOT_FOUND", 404, "API", "WARNING"
        )
        assert row["correlation_id"] == "corr-trip-404" == response.headers["X-Correlation-ID"]
        assert row["request_id"] == response.headers["X-Request-ID"] == response.json()["error"]["request_id"]
        assert row["employee_id"] == team["employee"]["employee_id"]
        assert row["source_component"] == "api GET /api/v1/trips/{trip_id}"     # template, not the id
        assert row["stack_trace"] is None                                       # 4xx: no stack trace

    def test_validation_error_stores_field_names_only(self, api_client, team, auth_header, test_engine) -> None:
        api_client.post("/api/v1/trips", headers=auth_header(team["employee"]),
                        json={"destination": "Pune", "start_date": "2000-01-01", "end_date": "2000-01-02",
                              "purpose": "Secret project codename"})
        row = error_rows(test_engine)[0]
        assert (row["error_code"], row["category"]) == ("VALIDATION_ERROR", "VALIDATION")
        assert row["context"]["fields"] == ["start_date"]
        assert "Secret project codename" not in str(row)                        # request values never stored

    def test_no_passwords_or_tokens_are_stored(self, api_client, team, auth_header, test_engine) -> None:
        api_client.post("/api/v1/auth/login",
                        json={"email": "rohan.mehta@veridian.example", "password": "WrongPassword-XYZ"})
        token = auth_header(team["employee"])["Authorization"].split()[1]
        api_client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}tampered"})
        rows = error_rows(test_engine)
        assert [row["error_code"] for row in rows] == ["INVALID_CREDENTIALS", "INVALID_TOKEN"]
        assert all(row["category"] == "AUTHENTICATION" for row in rows)
        dump = str(rows)
        assert "WrongPassword-XYZ" not in dump and token not in dump and "Bearer" not in dump

    def test_unexpected_error_is_500_with_stack_trace(self, team, auth_header, test_engine, monkeypatch) -> None:
        from app.services import trip_service

        def broken(*_args, **_kwargs):
            raise RuntimeError("simulated bug")

        monkeypatch.setattr(trip_service, "list_my_trips", broken)

        def override_get_db():
            from app.core.database import connection
            with connection(use_test_database=True) as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/api/v1/trips", headers=auth_header(team["employee"]))
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"
        row = error_rows(test_engine)[0]
        assert (row["severity"], row["category"]) == ("ERROR", "UNEXPECTED")
        # Type + code frames only; the exception's own text (which could hold SQL values) is not added.
        assert row["stack_trace"].startswith("RuntimeError\n") and "in broken" in row["stack_trace"]
        assert row["internal_message"] == "RuntimeError: An unexpected error occurred."

    def test_json_log_fallback_when_db_write_fails(self, api_client, team, auth_header, test_engine,
                                                    monkeypatch, caplog) -> None:
        def db_down(conn, record):
            raise RuntimeError("error_logs unavailable")

        monkeypatch.setattr(log_repo, "insert_error_log", db_down)
        with caplog.at_level(logging.WARNING, logger="traveldesk.errors"):
            response = api_client.get("/api/v1/trips/999999",
                                      headers={**auth_header(team["employee"]), "X-Correlation-ID": "corr-fallback"})
        assert response.status_code == 404                                     # original error still returned
        assert error_rows(test_engine) == []
        assert "error_log_write_failed" in caplog.text and "corr-fallback" in caplog.text


# --- Piyush/M2: class TestVeraLogs (AI, RAG and weather log rows) goes below ---

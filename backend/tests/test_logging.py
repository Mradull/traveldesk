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

# --- Piyush/M2: AI, RAG and weather log rows ---
import httpx                                                     # noqa: E402
import openai                                                    # noqa: E402
from pydantic import SecretStr                                   # noqa: E402

from app.ai import llm_client                                    # noqa: E402
from app.chat import chat_service, session_manager               # noqa: E402
from app.core.config import get_settings                         # noqa: E402
from app.schemas import AICallLog, AICallStatus, AIFeature, AIProvider   # noqa: E402
from tests.conftest import rows, tool_call                       # noqa: E402


def _auth_error() -> openai.AuthenticationError:
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return openai.AuthenticationError("bad key", response=httpx.Response(401, request=req), body=None)


@pytest.mark.usefixtures("vera_db")
class TestVeraLogs:
    """[P] Piyush: every Vera log row carries session / conversation / correlation ids."""

    def test_ai_call_logs_success_with_ids(self, employee, fake_llm):
        fake_llm("Which dates are you travelling?")
        sid = session_manager.open_session(employee).session_id
        reply = chat_service.handle_message(employee, sid, "Weather in Pune?", "req-1", "corr-ai")
        log = rows("SELECT * FROM ai_call_logs")[0]
        assert (log["feature"], log["status"], log["provider"], log["prompt_version"]) == \
            ("CHAT", "SUCCESS", get_settings().ai_provider, get_settings().prompt_version)
        assert log["session_id"] == sid and log["conversation_id"] == reply.conversation_id
        assert log["correlation_id"] == "corr-ai" and log["latency_ms"] >= 0
        conv = rows("SELECT request_id, correlation_id FROM chat_conversations")[0]
        assert conv == {"request_id": "req-1", "correlation_id": "corr-ai"}

    def test_llm_auth_failure_is_503_logged_and_turn_failed(self, client, auth, employee, fake_llm):
        fake_llm(_auth_error())
        h = auth(employee)
        sid = client.post("/api/v1/chat/sessions", headers=h).json()["session_id"]
        r = client.post(f"/api/v1/chat/sessions/{sid}/messages", headers={**h, "X-Correlation-ID": "corr-503"},
                        json={"message": "Weather in Pune?"})
        assert r.status_code == 503 and r.json()["error"]["code"] == "AI_AUTH_ERROR"
        assert "Everything else in TravelDesk works" in r.json()["error"]["message"]
        assert rows("SELECT status FROM ai_call_logs")[0]["status"] == "AUTH_ERROR"     # no retry on 401
        assert rows("SELECT status, error_code FROM chat_conversations")[0] == \
            {"status": "FAILED", "error_code": "AI_AUTH_ERROR"}
        assert rows("SELECT message_type FROM chat_messages ORDER BY message_id")[-1]["message_type"] == "ai_response"
        assert rows("SELECT correlation_id FROM ai_call_logs")[0]["correlation_id"] == "corr-503"
        err = rows("SELECT error_code, correlation_id FROM error_logs")[0]       # Joyal's handler (US-04)
        assert (err["error_code"], err["correlation_id"]) == ("AI_AUTH_ERROR", "corr-503")

    def test_timeout_is_retried_once(self, employee, fake_llm):
        fake_llm(TimeoutError("slow"), "Which dates are you travelling?")
        sid = session_manager.open_session(employee).session_id
        reply = chat_service.handle_message(employee, sid, "Weather in Pune?", "r", "c")
        assert reply.reply.startswith("Which dates")
        assert [r["status"] for r in rows("SELECT status FROM ai_call_logs ORDER BY log_id")] == ["TIMEOUT", "SUCCESS"]

    def test_rag_call_log_has_scores_and_citations(self, employee, fake_llm, policy_index):
        fake_llm("", "Meal lines above INR 1,500 need manager review [POL-6.2].")
        sid = session_manager.open_session(employee).session_id
        chat_service.handle_message(employee, sid, "What is the meal limit per line?", "r", "corr-rag")
        log = rows("SELECT * FROM rag_call_logs")[0]
        assert log["status"] == "SUCCESS" and log["correlation_id"] == "corr-rag" and log["session_id"] == sid
        assert "POL-6.2" in log["retrieved_ref_ids"] and len(log["retrieval_scores"]) == get_settings().rag_top_k
        assert log["citations_used"] == ["POL-6.2"]

    def test_weather_tool_log_links_to_the_turn(self, employee, fake_llm, weather_api):
        fake_llm(tool_call("get_weather_forecast", {"destination": "Bengaluru", "start_date": "2026-12-30",
                                                    "end_date": "2026-12-31"}, call_id="call-xyz"))
        sid = session_manager.open_session(employee).session_id
        reply = chat_service.handle_message(employee, sid, "Weather in Bengaluru 30-31 Dec?", "r", "corr-w")
        log = rows("SELECT * FROM weather_tool_logs")[0]
        assert (log["session_id"], log["conversation_id"], log["correlation_id"], log["tool_call_id"]) == \
            (sid, reply.conversation_id, "corr-w", "call-xyz")
        assert log["result_status"] == "FORECAST_OUT_OF_RANGE"

    def test_no_secrets_or_prompts_in_any_log_table(self, employee, fake_llm, monkeypatch):
        monkeypatch.setattr(get_settings(), "openrouter_api_key", SecretStr("sk-or-v1-SECRET123"))
        fake_llm(_auth_error())
        sid = session_manager.open_session(employee).session_id
        with pytest.raises(llm_client.LLMError):
            chat_service.handle_message(employee, sid, "Weather in Pune?", "r", "c")
        for table in ("ai_call_logs", "rag_call_logs", "weather_tool_logs", "error_logs", "chat_messages"):
            dump = str(rows(f"SELECT * FROM {table}"))
            assert "SECRET123" not in dump and "You are Vera" not in dump, table

    def test_log_write_failure_falls_back_to_json_log(self, caplog):
        def broken(conn, rec):
            raise RuntimeError("db down")
        rec = AICallLog(feature=AIFeature.CHAT, provider=AIProvider.OPENROUTER, model_name="m", prompt_version="v",
                        status=AICallStatus.SUCCESS, latency_ms=1, correlation_id="corr-fallback")
        log_repo.log_safely(broken, rec)                                    # must not raise
        assert "corr-fallback" in caplog.text and "log_write_failed" in caplog.text


@pytest.mark.usefixtures("vera_db")
class TestProviderErrorDetail:
    """[P] a failed AI call writes the provider's own reason to the application log (never the key)."""

    def test_failure_reason_is_logged_without_the_key(self, employee, fake_llm, monkeypatch, caplog):
        monkeypatch.setattr(get_settings(), "openrouter_api_key", SecretStr("sk-or-v1-SECRET123"))
        fake_llm(_auth_error())
        sid = session_manager.open_session(employee).session_id
        with pytest.raises(llm_client.LLMError):
            chat_service.handle_message(employee, sid, "Weather in Pune?", "r", "c")
        assert "ai_call_failed" in caplog.text and "AuthenticationError" in caplog.text
        assert "SECRET123" not in caplog.text

"""
insert_error_log() (Joyal); ai_call_logs, rag_call_logs, weather_tool_logs inserts (Piyush).

Owner: Joyal (M1) + Piyush (M2), see 'Shared files'  |  Spec: Agile Spec v2.0
"""

import json
import logging
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.schemas import AICallLog, ErrorLogRecord, RagCallLog, WeatherToolLog

log = logging.getLogger("traveldesk.logs")


# --- Joyal/M1: error_logs insert (spec > Logging, error storage and tracing; US-04) ---
def insert_error_log(conn: Connection, record: ErrorLogRecord) -> None:
    """Write one error_logs row. Call it in its OWN transaction (e.g. `with transaction() as conn:`),
    so the original request's rollback never removes the log row. The record must already be
    sanitized: never passwords, tokens, Authorization headers or API keys.

    Example (chat code, Piyush):
        with transaction() as conn:
            insert_error_log(conn, ErrorLogRecord(severity=ErrorSeverity.ERROR,
                source_component="chat.weather_tool", category=ErrorCategory.WEATHER,
                error_code=ErrorCode.WEATHER_TIMEOUT, safe_message="...", internal_message="...",
                correlation_id=..., session_id=..., conversation_id=...))
    """
    conn.execute(
        text(
            """
            INSERT INTO error_logs
                (severity, source_component, category, error_code, safe_message, internal_message,
                 http_status, retryable, request_id, correlation_id, tool_call_id, employee_id,
                 session_id, conversation_id, message_id, context, stack_trace)
            VALUES
                (:severity, :source_component, :category, :error_code, :safe_message, :internal_message,
                 :http_status, :retryable, :request_id, :correlation_id, :tool_call_id, :employee_id,
                 :session_id, :conversation_id, :message_id, CAST(:context AS JSONB), :stack_trace)
            """
        ),
        {
            "severity": record.severity.value,
            "source_component": record.source_component,
            "category": record.category.value,
            "error_code": record.error_code.value,
            "safe_message": record.safe_message,
            "internal_message": record.internal_message,
            "http_status": record.http_status,
            "retryable": record.retryable,
            "request_id": record.request_id,
            "correlation_id": record.correlation_id,
            "tool_call_id": record.tool_call_id,
            "employee_id": record.employee_id,
            "session_id": record.session_id,
            "conversation_id": record.conversation_id,
            "message_id": record.message_id,
            "context": json.dumps(record.context, default=str) if record.context is not None else None,
            "stack_trace": record.stack_trace,
        },
    )


# --- Piyush/M2: ai_call_logs, rag_call_logs, weather_tool_logs inserts go below ---
def log_safely(insert_fn: Callable[[Connection, Any], None], record: Any) -> None:
    """Run insert_fn(conn, record) in its OWN transaction and never raise.
    If PostgreSQL is down, the record goes to the JSON application log instead (same ids),
    so the trace is not lost and the chat turn still gets its answer."""
    from app.core.database import transaction  # late import: keeps this module free of engine setup
    try:
        with transaction() as conn:
            insert_fn(conn, record)
    except Exception as exc:  # noqa: BLE001 - logging must never break the request
        payload = record.model_dump(mode="json") if hasattr(record, "model_dump") else str(record)
        log.error(json.dumps({"event": "log_write_failed", "table_fn": insert_fn.__name__,
                              "error": type(exc).__name__, "record": payload}))


def insert_ai_call_log(conn: Connection, rec: AICallLog) -> None:
    """One row per LLM call (feature CHAT or SUMMARY). Prompts are never stored, only prompt_version."""
    conn.execute(text("""
        INSERT INTO ai_call_logs (feature, provider, model_name, prompt_version, status, latency_ms,
                                  prompt_tokens, completion_tokens, error_code,
                                  session_id, conversation_id, correlation_id)
        VALUES (:feature, :provider, :model_name, :prompt_version, :status, :latency_ms,
                :prompt_tokens, :completion_tokens, :error_code,
                :session_id, :conversation_id, :correlation_id)"""),
        rec.model_dump(mode="json"))


def insert_rag_call_log(conn: Connection, rec: RagCallLog) -> None:
    """One row per policy retrieval (written at the end of the turn so citations_used is known)."""
    conn.execute(text("""
        INSERT INTO rag_call_logs (session_id, conversation_id, correlation_id, query_text, top_k,
                                   retrieved_ref_ids, retrieval_scores, citations_used,
                                   status, error_code, latency_ms)
        VALUES (:session_id, :conversation_id, :correlation_id, :query_text, :top_k,
                :retrieved_ref_ids, :retrieval_scores, :citations_used,
                :status, :error_code, :latency_ms)"""),
        rec.model_dump(mode="json"))


def insert_weather_tool_log(conn: Connection, rec: WeatherToolLog) -> None:
    """One row per get_weather_forecast call, success or failure. No trip or business link."""
    conn.execute(text("""
        INSERT INTO weather_tool_logs (session_id, conversation_id, correlation_id, tool_call_id,
                                       destination_query, start_date, end_date, resolved_location,
                                       provider, http_status, latency_ms, result_status, error_code,
                                       cache_hit, retrieved_at)
        VALUES (:session_id, :conversation_id, :correlation_id, :tool_call_id,
                :destination_query, :start_date, :end_date, :resolved_location,
                :provider, :http_status, :latency_ms, :result_status, :error_code,
                :cache_hit, :retrieved_at)"""),
        rec.model_dump(mode="json"))

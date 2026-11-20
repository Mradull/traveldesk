"""
insert_error_log() (Joyal); ai_call_logs, rag_call_logs, weather_tool_logs inserts (Piyush).

Owner: Joyal (M1) + Piyush (M2), see 'Shared files'  |  Spec: Agile Spec v2.0
"""

import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.schemas import ErrorLogRecord


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

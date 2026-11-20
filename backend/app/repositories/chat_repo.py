"""
repositories/chat_repo.py - all SQL for Vera's chat tables (owner: Piyush, M2).

Tables: chat_sessions, chat_conversations, chat_messages (migration 003).
Only these tables are touched here: nothing in this file can read trips, tickets,
expenses or evidence (Vera isolation). Every query uses bound parameters.
Time comparisons use the database clock (now()) so every backend agrees.
"""
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

_SESSION_COLS = """session_id, employee_id, status, close_reason, summary, summarized_upto_turn,
                   started_at, last_activity_at, closed_at"""


# ----------------------------------------------------------------------------- sessions
def replace_active_sessions(conn: Connection, employee_id: int) -> None:
    """Close the employee's ACTIVE session (if any) with REPLACED before a new one is opened."""
    conn.execute(text("""
        UPDATE chat_sessions SET status = 'CLOSED', close_reason = 'REPLACED', closed_at = now()
        WHERE employee_id = :employee_id AND status = 'ACTIVE'"""), {"employee_id": employee_id})


def create_session(conn: Connection, employee_id: int) -> RowMapping:
    """Insert a new ACTIVE session and return it."""
    return conn.execute(text(f"""
        INSERT INTO chat_sessions (employee_id) VALUES (:employee_id)
        RETURNING {_SESSION_COLS}"""), {"employee_id": employee_id}).mappings().one()


def get_session(conn: Connection, session_id: UUID, idle_minutes: int,
                for_update: bool = False) -> RowMapping | None:
    """One session plus is_idle (no activity for longer than idle_minutes).
    for_update=True locks the row so two messages to the same session get distinct turns."""
    lock = " FOR UPDATE" if for_update else ""
    return conn.execute(text(f"""
        SELECT {_SESSION_COLS},
               (now() - last_activity_at) > make_interval(mins => :idle) AS is_idle
        FROM chat_sessions WHERE session_id = :session_id{lock}"""),
        {"session_id": session_id, "idle": idle_minutes}).mappings().first()


def end_session(conn: Connection, session_id: UUID, status: str, reason: str) -> RowMapping:
    """Mark an ACTIVE session CLOSED or EXPIRED. Returns the row (unchanged if it had already ended)."""
    row = conn.execute(text(f"""
        UPDATE chat_sessions SET status = :status, close_reason = :reason, closed_at = now()
        WHERE session_id = :session_id AND status = 'ACTIVE'
        RETURNING {_SESSION_COLS}"""), {"session_id": session_id, "status": status, "reason": reason}
    ).mappings().first()
    if row is None:   # already ended: return it as it is (close is idempotent)
        row = conn.execute(text(f"SELECT {_SESSION_COLS} FROM chat_sessions WHERE session_id = :s"),
                           {"s": session_id}).mappings().one()
    return row


def touch_session(conn: Connection, session_id: UUID) -> None:
    """Record activity so the 60-minute idle timer restarts."""
    conn.execute(text("UPDATE chat_sessions SET last_activity_at = now() WHERE session_id = :s"),
                 {"s": session_id})


def expire_idle_sessions(conn: Connection, idle_minutes: int) -> int:
    """Scheduler job: every ACTIVE session idle longer than idle_minutes becomes EXPIRED."""
    result = conn.execute(text("""
        UPDATE chat_sessions SET status = 'EXPIRED', close_reason = 'IDLE_TIMEOUT', closed_at = now()
        WHERE status = 'ACTIVE' AND (now() - last_activity_at) > make_interval(mins => :idle)"""),
        {"idle": idle_minutes})
    return result.rowcount


def list_ended_sessions(conn: Connection, employee_id: int) -> list[RowMapping]:
    """Past chats: the employee's CLOSED/EXPIRED sessions that have at least one turn, newest first.
    preview = first employee message cut to 80 characters (already masked when stored)."""
    return list(conn.execute(text("""
        SELECT s.session_id, s.status, s.close_reason, s.started_at, s.last_activity_at, s.closed_at,
               (SELECT count(*) FROM chat_conversations c WHERE c.session_id = s.session_id) AS turn_count,
               COALESCE(left((SELECT m.content FROM chat_messages m
                               WHERE m.session_id = s.session_id AND m.message_type = 'human_message'
                               ORDER BY m.message_id LIMIT 1), 80), '') AS preview
        FROM chat_sessions s
        WHERE s.employee_id = :employee_id AND s.status <> 'ACTIVE'
          AND EXISTS (SELECT 1 FROM chat_conversations c WHERE c.session_id = s.session_id)
        ORDER BY s.started_at DESC"""), {"employee_id": employee_id}).mappings())


def update_summary(conn: Connection, session_id: UUID, summary: str, upto_turn: int) -> None:
    """Store the rolling summary of this session's older turns."""
    conn.execute(text("""
        UPDATE chat_sessions SET summary = :summary, summarized_upto_turn = :upto
        WHERE session_id = :s"""), {"summary": summary, "upto": upto_turn, "s": session_id})


# ----------------------------------------------------------------------------- turns
def create_conversation(conn: Connection, session_id: UUID, request_id: str | None,
                        correlation_id: str | None, model_name: str) -> RowMapping:
    """Start the next turn of a session. Caller must hold the session row lock (get_session
    for_update=True); UNIQUE(session_id, turn_number) is the safety net."""
    return conn.execute(text("""
        INSERT INTO chat_conversations (session_id, turn_number, request_id, correlation_id, model_name)
        VALUES (:s, (SELECT COALESCE(max(turn_number), 0) + 1 FROM chat_conversations WHERE session_id = :s),
                :request_id, :correlation_id, :model_name)
        RETURNING conversation_id, turn_number, created_at"""),
        {"s": session_id, "request_id": request_id, "correlation_id": correlation_id,
         "model_name": model_name}).mappings().one()


def finish_conversation(conn: Connection, conversation_id: UUID, *, intent: str, status: str,
                        guardrail_status: str, guardrail_reasons: list[str],
                        error_code: str | None, latency_ms: int) -> None:
    """Write the outcome of a turn once it is complete."""
    conn.execute(text("""
        UPDATE chat_conversations
        SET intent = :intent, status = :status, guardrail_status = :guardrail_status,
            guardrail_reasons = :guardrail_reasons, error_code = :error_code, latency_ms = :latency_ms
        WHERE conversation_id = :c"""),
        {"c": conversation_id, "intent": intent, "status": status, "guardrail_status": guardrail_status,
         "guardrail_reasons": guardrail_reasons, "error_code": error_code, "latency_ms": latency_ms})


def last_intent(conn: Connection, session_id: UUID, before_turn: int) -> str | None:
    """Intent of the previous turn in THIS session (for follow-up inheritance)."""
    return conn.execute(text("""
        SELECT intent FROM chat_conversations
        WHERE session_id = :s AND turn_number < :t AND intent IS NOT NULL
        ORDER BY turn_number DESC LIMIT 1"""), {"s": session_id, "t": before_turn}).scalar()


# ----------------------------------------------------------------------------- messages
def add_message(conn: Connection, *, session_id: UUID, conversation_id: UUID, sequence_no: int,
                message_type: str, content: str, tool_name: str | None = None,
                tool_call_id: str | None = None, tool_args: dict[str, Any] | None = None,
                metadata: dict[str, Any] | None = None) -> int:
    """Append one ordered event to a turn and return its message_id."""
    return conn.execute(text("""
        INSERT INTO chat_messages (session_id, conversation_id, sequence_no, message_type, content,
                                   tool_name, tool_call_id, tool_args, metadata)
        VALUES (:session_id, :conversation_id, :sequence_no, :message_type, :content,
                :tool_name, :tool_call_id, CAST(:tool_args AS JSONB), CAST(:metadata AS JSONB))
        RETURNING message_id"""),
        {"session_id": session_id, "conversation_id": conversation_id, "sequence_no": sequence_no,
         "message_type": message_type, "content": content, "tool_name": tool_name,
         "tool_call_id": tool_call_id,
         "tool_args": json.dumps(tool_args) if tool_args is not None else None,
         "metadata": json.dumps(metadata, default=str) if metadata is not None else None}).scalar_one()


def list_messages(conn: Connection, session_id: UUID, from_turn: int = 1,
                  to_turn: int | None = None) -> list[RowMapping]:
    """Messages of ONE session in order, optionally only turns from_turn..to_turn."""
    return list(conn.execute(text("""
        SELECT m.message_id, m.session_id, m.conversation_id, c.turn_number, m.sequence_no,
               m.message_type, m.content, m.tool_name, m.tool_call_id, m.tool_args, m.metadata, m.created_at
        FROM chat_messages m JOIN chat_conversations c ON c.conversation_id = m.conversation_id
        WHERE m.session_id = :s AND c.turn_number >= :from_turn
          AND (CAST(:to_turn AS INT) IS NULL OR c.turn_number <= :to_turn)
        ORDER BY c.turn_number, m.sequence_no"""),
        {"s": session_id, "from_turn": from_turn, "to_turn": to_turn}).mappings())

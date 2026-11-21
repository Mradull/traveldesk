"""
chat/session_manager.py - lifecycle and ownership of Vera chat sessions (owner: Piyush, M2).

  open    POST /chat/sessions            closes any ACTIVE session (REPLACED), creates a new one
  close   POST /chat/sessions/{id}/close CLOSED / USER_CLOSED; messages are kept
  idle    > 60 minutes since last_activity_at -> EXPIRED / IDLE_TIMEOUT, next message gets 410
  owner   a session that is not the caller's returns 404 (ids cannot be probed)
  history only the employee's own ended chats; read-only; never loaded into a new session
"""
from uuid import UUID

from app.core.config import get_settings
from app.core.database import transaction
from app.core.errors import AppError
from app.repositories import chat_repo
from app.schemas import (ChatHistoryOut, ChatMessageOut, ChatSessionCloseOut, ChatSessionListItemOut, ChatSessionOut,
                         ChatSessionStatus, CurrentUser, ErrorCode)



def _idle_minutes() -> int:
    """CHAT_IDLE_TIMEOUT_MINUTES, read at call time."""
    return get_settings().chat_idle_timeout_minutes


def _not_found() -> AppError:
    return AppError(ErrorCode.NOT_FOUND, 404, "Chat not found")


def _owned(conn, user: CurrentUser, session_id: UUID, for_update: bool = False):
    """Load a session and check it belongs to the caller (404 otherwise)."""
    row = chat_repo.get_session(conn, session_id, _idle_minutes(), for_update=for_update)
    if row is None or row["employee_id"] != user.employee_id:
        raise _not_found()
    return row


def open_session(user: CurrentUser) -> ChatSessionOut:
    """New ACTIVE session; an older ACTIVE one (e.g. another tab) is closed as REPLACED."""
    with transaction() as conn:
        chat_repo.replace_active_sessions(conn, user.employee_id)
        row = chat_repo.create_session(conn, user.employee_id)
    return ChatSessionOut(session_id=row["session_id"], status=row["status"], idle_timeout_minutes=_idle_minutes(),
                          started_at=row["started_at"])


def close_session(user: CurrentUser, session_id: UUID) -> ChatSessionCloseOut:
    """X button. Closing an already ended session just returns its final state."""
    with transaction() as conn:
        _owned(conn, user, session_id, for_update=True)
        row = chat_repo.end_session(conn, session_id, "CLOSED", "USER_CLOSED")
    return ChatSessionCloseOut(session_id=row["session_id"], status=row["status"],
                               close_reason=row["close_reason"], closed_at=row["closed_at"])


def ensure_active(user: CurrentUser, session_id: UUID) -> None:
    """Before a turn: owner (404), still ACTIVE (410 SESSION_CLOSED), not idle (410 SESSION_EXPIRED).
    An idle session is marked EXPIRED and COMMITTED before the 410 is raised."""
    expired = False
    with transaction() as conn:
        row = _owned(conn, user, session_id, for_update=True)
        if row["status"] == ChatSessionStatus.EXPIRED.value:
            expired = True
        elif row["status"] == ChatSessionStatus.CLOSED.value:
            raise AppError(ErrorCode.SESSION_CLOSED, 410, "This chat has ended. A new chat will start.")
        elif row["is_idle"]:
            chat_repo.end_session(conn, session_id, "EXPIRED", "IDLE_TIMEOUT")
            expired = True
    if expired:
        raise AppError(ErrorCode.SESSION_EXPIRED, 410, "This chat expired after 60 idle minutes. A new chat will start.")


def list_past(user: CurrentUser) -> list[ChatSessionListItemOut]:
    """Past chats: the caller's ended sessions with at least one message, newest first."""
    with transaction() as conn:
        rows = chat_repo.list_ended_sessions(conn, user.employee_id)
    return [ChatSessionListItemOut(**r) for r in rows]


def history(user: CurrentUser, session_id: UUID) -> ChatHistoryOut:
    """Read-only transcript of one of the caller's sessions (all four message types, in order)."""
    with transaction() as conn:
        session = _owned(conn, user, session_id)
        rows = chat_repo.list_messages(conn, session_id)
    return ChatHistoryOut(session_id=session_id, status=session["status"],
                          read_only=session["status"] != ChatSessionStatus.ACTIVE.value,
                          messages=[ChatMessageOut(**r) for r in rows])

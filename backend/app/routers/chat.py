"""
routers/chat.py - Vera's five endpoints (owner: Piyush, M2). Employee role only:
require_employee returns 403 FORBIDDEN to managers, even if the UI is bypassed.
Thin router: parse with schemas.py, call one chat function, return an ...Out model.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.chat import chat_service, session_manager
from app.core.deps import require_employee
from app.schemas import (ChatHistoryOut, ChatMessageRequest, ChatReplyOut, ChatSessionCloseOut, ChatSessionListItemOut,
                         ChatSessionOut, CurrentUser, ErrorResponse)

# Every error comes back as the standard envelope; listing it makes Swagger show the shape.
router = APIRouter(prefix="/chat", tags=["Vera chat"],
                   responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 410, 422, 429, 503)})


@router.post("/sessions", response_model=ChatSessionOut, status_code=201)
def open_session(user: CurrentUser = Depends(require_employee)):
    """Open Vera: closes any other ACTIVE chat of this employee (REPLACED) and starts a fresh one."""
    return session_manager.open_session(user)


@router.get("/sessions", response_model=list[ChatSessionListItemOut])
def past_chats(user: CurrentUser = Depends(require_employee)):
    """Past chats: the caller's ended chats, newest first (read-only)."""
    return session_manager.list_past(user)


@router.get("/sessions/{session_id}/messages", response_model=ChatHistoryOut)
def session_messages(session_id: UUID, user: CurrentUser = Depends(require_employee)):
    """Transcript of one of the caller's chats; another employee's id returns 404."""
    return session_manager.history(user, session_id)


@router.post("/sessions/{session_id}/messages", response_model=ChatReplyOut)
def send_message(session_id: UUID, body: ChatMessageRequest, request: Request,
                 user: CurrentUser = Depends(require_employee)):
    """One Vera turn. 410 when the chat was closed or idle for 60 minutes (the UI starts a new one)."""
    return chat_service.handle_message(user, session_id, body.message,
                                       getattr(request.state, "request_id", None),
                                       getattr(request.state, "correlation_id", None))


@router.post("/sessions/{session_id}/close", response_model=ChatSessionCloseOut)
def close_session(session_id: UUID, user: CurrentUser = Depends(require_employee)):
    """X button: CLOSED / USER_CLOSED. The messages stay readable in Past chats."""
    return session_manager.close_session(user, session_id)

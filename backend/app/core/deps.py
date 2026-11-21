"""
get_db, get_current_user (Bearer token -> CurrentUser, role re-read from DB), require_employee, require_manager.
403 for a wrong role; 404 for records that belong to someone else.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from collections.abc import Iterator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Connection

from app.core.database import connection
from app.core.errors import AppError
from app.core.security import InvalidTokenError, TokenExpiredError, decode_access_token
from app.schemas import CurrentUser, ErrorCode, Role
from app.services.auth_service import get_current_employee

_bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Connection]:
    with connection() as db:
        yield db


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Connection = Depends(get_db),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            ErrorCode.UNAUTHENTICATED,
            401,
            "A bearer access token is required.",
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except TokenExpiredError as exc:
        raise AppError(
            ErrorCode.TOKEN_EXPIRED,
            401,
            "The access token has expired. Please sign in again.",
        ) from exc
    except InvalidTokenError as exc:
        raise AppError(
            ErrorCode.INVALID_TOKEN,
            401,
            "The access token is invalid.",
        ) from exc
    try:
        employee_id = payload.employee_id
    except (TypeError, ValueError) as exc:
        raise AppError(
            ErrorCode.INVALID_TOKEN,
            401,
            "The access token is invalid.",
        ) from exc
    user = get_current_employee(db, employee_id)
    request.state.employee_id = user.employee_id          # lets error_logs record who was calling
    return user


def require_employee(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != Role.EMPLOYEE:
        raise AppError(
            ErrorCode.FORBIDDEN,
            403,
            "This action is available to employees only.",
        )
    return user


def require_manager(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != Role.MANAGER:
        raise AppError(
            ErrorCode.FORBIDDEN,
            403,
            "This action is available to managers only.",
        )
    return user

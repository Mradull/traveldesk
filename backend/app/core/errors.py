"""
AppError and handlers that return the common error envelope and emit sanitized JSON logs.
Database persistence is deferred until the shared error_logs migration and repository are ready.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas import ErrorCode, ErrorResponse

logger = logging.getLogger("traveldesk.errors")


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        http_status: int,
        safe_message: str,
        retryable: bool = False,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.http_status = http_status
        self.safe_message = safe_message
        self.retryable = retryable
        self.details = details


def _request_ids(request: Request) -> tuple[str | None, str | None]:
    return (
        getattr(request.state, "request_id", None),
        getattr(request.state, "correlation_id", None),
    )


def _log_error(
    request: Request,
    code: ErrorCode,
    http_status: int,
    error_type: str,
) -> None:
    request_id, correlation_id = _request_ids(request)
    logger.error(
        json.dumps(
            {
                "severity": "ERROR",
                "source_component": "api",
                "error_code": code.value,
                "http_status": http_status,
                "error_type": error_type,
                "request_id": request_id,
                "correlation_id": correlation_id,
            },
            separators=(",", ":"),
        )
    )


def _error_response(
    request: Request,
    code: ErrorCode,
    message: str,
    status_code: int,
    *,
    details: list[dict[str, Any]] | None = None,
    retryable: bool = False,
) -> JSONResponse:
    request_id, correlation_id = _request_ids(request)
    body = ErrorResponse(
        error={
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "retryable": retryable,
        }
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


# Rules in schemas.py that check several fields together (model validators) have no single field
# in their error location. The spec wants every message shown under its field (e.g. trip dates,
# review_comment, expenses), so these exact schemas.py messages are mapped to the field they are about.
_MODEL_RULE_FIELDS: tuple[tuple[str, str], ...] = (
    ("start_date must be today or a future date", "start_date"),              # TripBase
    ("A trip cannot start more than one year from today", "start_date"),      # TripBase
    ("end_date must be later than start_date", "end_date"),                   # TripBase
    ("A trip can last at most", "end_date"),                                  # TripBase
    ("review_comment of at least", "review_comment"),                         # Trip/TicketDecisionRequest
    ("rejection_reason is", "rejection_reason"),                              # TicketDecisionRequest
    ("Each expense line needs its own receipt photo", "expenses"),            # TicketCreate
    ("The same invoice number appears twice", "expenses"),                    # TicketCreate
)
_PYDANTIC_VALUE_ERROR_PREFIX = "Value error, "


def _validation_detail(error: dict[str, Any]) -> dict[str, str]:
    """Turn one Pydantic error into {"field": ..., "msg": ...} for the error envelope.

    Example: TripCreate with end_date == start_date
      before: {"field": "",         "msg": "Value error, end_date must be later than start_date"}
      after:  {"field": "end_date", "msg": "end_date must be later than start_date"}
    Nested paths keep their prefix, e.g. "expenses.0.expense_date".
    """
    field = ".".join(str(part) for part in error["loc"] if part != "body")
    message = str(error["msg"]).removeprefix(_PYDANTIC_VALUE_ERROR_PREFIX)
    if error.get("type") == "value_error":
        for message_start, rule_field in _MODEL_RULE_FIELDS:
            if message.startswith(message_start) and field.rsplit(".", 1)[-1] != rule_field:
                field = f"{field}.{rule_field}" if field else rule_field
                break
    return {"field": field, "msg": message}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        _log_error(request, exc.code, exc.http_status, type(exc).__name__)
        return _error_response(
            request,
            exc.code,
            exc.safe_message,
            exc.http_status,
            details=exc.details,
            retryable=exc.retryable,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [_validation_detail(error) for error in exc.errors()]
        _log_error(request, ErrorCode.VALIDATION_ERROR, 422, type(exc).__name__)
        return _error_response(
            request,
            ErrorCode.VALIDATION_ERROR,
            "Request validation failed.",
            422,
            details=details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        mappings = {
            401: (ErrorCode.UNAUTHENTICATED, "Authentication is required."),
            403: (ErrorCode.FORBIDDEN, "You do not have permission to perform this action."),
            404: (ErrorCode.NOT_FOUND, "The requested resource was not found."),
            405: (ErrorCode.METHOD_NOT_ALLOWED, "This method is not allowed."),
        }
        code, message = mappings.get(
            exc.status_code,
            (ErrorCode.INTERNAL_ERROR, "The request could not be completed."),
        )
        _log_error(request, code, exc.status_code, type(exc).__name__)
        return _error_response(request, code, message, exc.status_code)

    @app.exception_handler(OperationalError)
    async def database_error_handler(
        request: Request, exc: OperationalError
    ) -> JSONResponse:
        _log_error(request, ErrorCode.DATABASE_UNAVAILABLE, 503, type(exc).__name__)
        return _error_response(
            request,
            ErrorCode.DATABASE_UNAVAILABLE,
            "The database is temporarily unavailable.",
            503,
            retryable=True,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        _log_error(request, ErrorCode.INTERNAL_ERROR, 500, type(exc).__name__)
        return _error_response(
            request,
            ErrorCode.INTERNAL_ERROR,
            "An unexpected error occurred.",
            500,
            retryable=False,
        )

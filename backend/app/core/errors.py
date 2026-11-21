"""
AppError and handlers that return the common error envelope, store every error in error_logs
(own transaction) and fall back to the JSON application log if that write fails.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0  (US-04; Error and edge-case handling; Logging, error storage and tracing)

Envelope (every 4xx/5xx):  {"error": {code, message, details, request_id, correlation_id, retryable}}
Never stored or logged: passwords, tokens, Authorization headers, API keys, request bodies.
"""

import json
import logging
import traceback
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.database import transaction
from app.repositories import log_repo
from app.schemas import ErrorCategory, ErrorCode, ErrorLogRecord, ErrorResponse, ErrorSeverity

logger = logging.getLogger("traveldesk.errors")


class AppError(Exception):
    """Raised by services: a stable ErrorCode, the HTTP status and a safe user-facing message."""

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


# ============================================================================= error storage
def _category(code: ErrorCode, http_status: int) -> ErrorCategory:
    """error_logs.category: which kind of failure happened (schemas.ErrorCategory)."""
    name = code.value
    if name.startswith("WEATHER_") or name == "FORECAST_OUT_OF_RANGE":
        return ErrorCategory.WEATHER
    if name.startswith("AI_"):
        return ErrorCategory.LLM
    if name == "POLICY_RETRIEVAL_FAILED":
        return ErrorCategory.RAG
    if code == ErrorCode.DATABASE_UNAVAILABLE:
        return ErrorCategory.DATABASE
    if http_status == 422:
        return ErrorCategory.VALIDATION
    if http_status == 401:
        return ErrorCategory.AUTHENTICATION
    if http_status == 403:
        return ErrorCategory.AUTHORIZATION
    if http_status == 429:
        return ErrorCategory.RATE_LIMIT
    if http_status in (404, 405):
        return ErrorCategory.API
    if http_status >= 500:
        return ErrorCategory.UNEXPECTED
    return ErrorCategory.BUSINESS_RULE                       # 409, 410, 413, 415 ...


def _route_template(request: Request) -> str:
    """'/api/v1/trips/{trip_id}' rather than '/api/v1/trips/7' (no ids or values in the log)."""
    parts = request.url.path.split("/")
    for name, value in request.path_params.items():
        parts = [f"{{{name}}}" if part == str(value) else part for part in parts]
    return "/".join(parts)


def _write_error_row(record: ErrorLogRecord) -> None:
    with transaction() as conn:                              # own transaction, never the request's
        log_repo.insert_error_log(conn, record)


async def _store_error(
    request: Request,
    exc: Exception,
    code: ErrorCode,
    http_status: int,
    safe_message: str,
    retryable: bool,
    details: list[dict[str, Any]] | None,
) -> None:
    """Build a sanitized ErrorLogRecord, write it to error_logs, or log it as JSON if that fails."""
    settings = get_settings()
    request_id, correlation_id = _request_ids(request)
    template = _route_template(request)
    context: dict[str, Any] = {"method": request.method, "path": template}
    if details:
        context["fields"] = [detail.get("field") for detail in details]      # field names only, no values
    if isinstance(exc, DBAPIError):
        internal = f"{type(exc).__name__}: {getattr(getattr(exc.orig, 'diag', None), 'message_primary', None)}"
    else:
        internal = f"{type(exc).__name__}: {safe_message}"
    stack = None
    if http_status >= 500 and settings.error_log_stack_traces:
        # Frames only (file, line, function); the exception text could contain SQL parameters.
        stack = type(exc).__name__ + "\n" + "".join(traceback.format_tb(exc.__traceback__))
    record = ErrorLogRecord(
        severity=ErrorSeverity.ERROR if http_status >= 500 else ErrorSeverity.WARNING,
        source_component=f"api {request.method} {template}",
        category=_category(code, http_status),
        error_code=code,
        safe_message=safe_message,
        internal_message=internal,
        http_status=http_status,
        retryable=retryable,
        request_id=request_id,
        correlation_id=correlation_id,
        employee_id=getattr(request.state, "employee_id", None),
        context=context,
        stack_trace=stack,
    )
    summary = {key: value for key, value in record.model_dump(mode="json").items() if key != "stack_trace"}
    logger.log(logging.ERROR if http_status >= 500 else logging.WARNING, json.dumps({"event": "api_error", **summary}))
    if not settings.error_log_to_db:
        return
    try:
        await run_in_threadpool(_write_error_row, record)
    except Exception as write_error:  # noqa: BLE001 - logging must never hide the original error
        logger.error(json.dumps({"event": "error_log_write_failed",
                                 "write_error_type": type(write_error).__name__, **summary}))


async def _handle(
    request: Request,
    exc: Exception,
    code: ErrorCode,
    http_status: int,
    message: str,
    *,
    details: list[dict[str, Any]] | None = None,
    retryable: bool = False,
) -> JSONResponse:
    """Store the error, then return the envelope (the response never depends on the log write)."""
    await _store_error(request, exc, code, http_status, message, retryable, details)
    return _error_response(request, code, message, http_status, details=details, retryable=retryable)


# ============================================================================= validation details
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

# Database trigger errors (migration 006) -> the envelope the API would have returned itself.
_TRIGGER_ERRORS: dict[str, tuple[ErrorCode, int, str]] = {
    "TICKET_READ_ONLY": (ErrorCode.TICKET_READ_ONLY, 409, "A decided ticket cannot be changed."),
    "ALREADY_DECIDED": (ErrorCode.ALREADY_DECIDED, 409, "This record has already been decided."),
    "TRIP_NOT_ACTIVE": (ErrorCode.TRIP_NOT_ACTIVE, 409, "Tickets can only be raised on an Approved - Active trip."),
    "EXPENSE_DATE_BEFORE_TRIP_CREATED": (
        ErrorCode.EXPENSE_DATE_BEFORE_TRIP_CREATED, 422, "Expense date is before this trip was created",
    ),
}


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


# ============================================================================= handlers
def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return await _handle(request, exc, exc.code, exc.http_status, exc.safe_message,
                             details=exc.details, retryable=exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [_validation_detail(error) for error in exc.errors()]
        return await _handle(request, exc, ErrorCode.VALIDATION_ERROR, 422, "Request validation failed.",
                             details=details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        mappings = {
            401: (ErrorCode.UNAUTHENTICATED, "Authentication is required."),
            403: (ErrorCode.FORBIDDEN, "You do not have permission to perform this action."),
            404: (ErrorCode.NOT_FOUND, "The requested resource was not found."),
            405: (ErrorCode.METHOD_NOT_ALLOWED, "This method is not allowed."),
        }
        code, message = mappings.get(exc.status_code, (ErrorCode.INTERNAL_ERROR, "The request could not be completed."))
        return await _handle(request, exc, code, exc.status_code, message)

    @app.exception_handler(OperationalError)
    async def database_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
        # The error_logs write will fail too while the DB is down -> JSON log fallback (spec).
        return await _handle(request, exc, ErrorCode.DATABASE_UNAVAILABLE, 503,
                             "The database is temporarily unavailable.", retryable=True)

    @app.exception_handler(DBAPIError)
    async def database_rule_handler(request: Request, exc: DBAPIError) -> JSONResponse:
        """Backstop for the migration 006 triggers: their error MESSAGE is an ErrorCode."""
        code_name = getattr(getattr(exc.orig, "diag", None), "message_primary", None)
        if code_name in _TRIGGER_ERRORS:
            code, http_status, message = _TRIGGER_ERRORS[code_name]
            return await _handle(request, exc, code, http_status, message)
        return await _handle(request, exc, ErrorCode.INTERNAL_ERROR, 500, "An unexpected error occurred.")

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return await _handle(request, exc, ErrorCode.INTERNAL_ERROR, 500, "An unexpected error occurred.")

"""
schema.py  —  TravelDesk data contract (save as backend/app/schemas.py)
=====================================================================
Project : AI-Powered Travel & Expense Management (EY Capstone, Project 04)
Version : matches Agile Spec v2.0 (final)
Purpose : ONE file that defines the shape of every piece of data that moves between
          the components of the system:

    React (Employee view / Manager view)
        |  HTTPS JSON + "Authorization: Bearer <JWT>"
        v
    FastAPI routers  ->  business services  ->  business repositories  ->  PostgreSQL (local, pgAdmin)
                     ->  chat service (Vera) ->  chat repository / RAG / WeatherService / LLM
                                                 (Vera NEVER touches business repositories)

How to read the names:
  * ...Create / ...Update / ...Request  -> data coming IN from React (validated here).
  * ...Out                              -> data going OUT to React (FastAPI response_model).
  * everything else                     -> internal objects passed between services
                                           (tool inputs/outputs, LLM output, log records).

Golden rules this file enforces:
  1. Pydantic validates every request at the API boundary BEFORE any service or SQL runs.
     Rules that need the database (trip state, trip creation date, evidence ownership)
     are checked in the services and reported with the same error envelope.
  2. Business-tunable numbers (review thresholds, auto-complete days, timeouts) live in
     app/core/config.py (.env). Structural limits that never change per environment
     live in section 0 below.
  3. The LLM never fills a field that decides anything. Approval fields come only from the
     policy engine or a manager; ForecastBasis is built by code from the weather API.

Requires: pydantic >= 2.6   (no extra packages: e-mail is checked with a simple pattern)
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

# =============================================================================
# 0. STRUCTURAL LIMITS  (mirror the business document; rule ids in brackets)
# =============================================================================
MAX_TRIP_DAYS = 30                 # [POL-3.2] start and end date both count
MAX_DAYS_IN_ADVANCE = 365          # [POL-3.2] a trip may START at most one year from today
MIN_PURPOSE_CHARS, MAX_PURPOSE_CHARS = 10, 500               # [POL-3.4]
MAX_LINE_AMOUNT_INR = Decimal("200000.00")                   # [POL-6.3] hard cap -> 422
MIN_LINES_PER_TICKET, MAX_LINES_PER_TICKET = 1, 20           # [POL-5.4]
MIN_REVIEW_COMMENT_CHARS, MAX_REVIEW_COMMENT_CHARS = 10, 1000  # [POL-3.6] / [POL-9.4]
MAX_CHAT_MESSAGE_CHARS = 1000      # chat input guardrail
MIN_PASSWORD_CHARS, MAX_PASSWORD_CHARS = 8, 128
WEATHER_MAX_SPAN_DAYS = 30         # longest date range one weather request may cover

# Allowed receipt-photo types [POL-7.1]. evidence_service ALSO checks the file signature
# (magic bytes), so a renamed PDF cannot pass as a JPEG.
ALLOWED_EVIDENCE_MIME_TYPES = ("image/jpeg", "image/png", "image/webp")

# Destination: letters (incl. accented), spaces and . , ' ( ) -   e.g. "St. John's", "Kochi, India"
DESTINATION_PATTERN = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ .,'()\-]{1,99}$")
# Optional invoice number printed on the receipt, e.g. "INV-88231", "IXR/2026/0045"   [POL-7.2]
INVOICE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/]{2,49}$")
# Simple e-mail shape check (the database lookup is the real check)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def today() -> date:
    """Single place to get 'today' so tests can monkeypatch it (freeze time).
    Uses the TZ setting from .env (default Asia/Kolkata), not the machine's clock zone,
    so every teammate's backend agrees on the date. (Windows: pip install tzdata.)"""
    return datetime.now(ZoneInfo(os.getenv("TZ", "Asia/Kolkata"))).date()


# Money is received as Decimal (exact, no float rounding) but sent to React as a JSON number.
MoneyOut = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]


# =============================================================================
# 1. ENUMS  — every value matches a CHECK constraint in the database.
#    (str, Enum) means the value is stored and sent as plain text, e.g. "APPROVED".
# =============================================================================
class Role(str, Enum):
    """Two application views only. A MANAGER account uses only the Manager view."""
    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"


class ApprovalStatus(str, Enum):
    """Manager decision on a TRAVEL REQUEST (travel_requests.approval_status)."""
    IN_PROGRESS = "IN_PROGRESS"   # waiting for the manager (UI label "In Progress")
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TripState(str, Enum):
    """Sub-status that exists ONLY when approval_status = APPROVED (travel_requests.trip_state)."""
    ACTIVE = "ACTIVE"             # tickets can be raised and expenses added
    COMPLETED = "COMPLETED"       # closed: no new tickets, no new expenses


class CompletionType(str, Enum):
    """Who completed the trip. Employees can never complete a trip."""
    MANAGER = "MANAGER"           # manager clicked "Mark completed" (on/after end date)
    AUTO = "AUTO"                 # scheduler: 90 days after the trip START date


class Decision(str, Enum):
    """What a manager submits for a trip or a ticket (request body)."""
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TicketDecisionValue(str, Enum):
    """What is written to ticket_approvals (audit history; includes system decisions)."""
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    AUTO_APPROVED = "AUTO_APPROVED"   # reviewer_type = SYSTEM


class ReviewerType(str, Enum):
    MANAGER = "MANAGER"
    SYSTEM = "SYSTEM"


class RejectionReason(str, Enum):
    """Required category when a manager rejects a ticket [POL-9.4]."""
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"     # e.g. blurred or cut-off photo
    INCORRECT_EVIDENCE = "INCORRECT_EVIDENCE"           # photo does not match the line
    UNCLEAR_PURPOSE = "UNCLEAR_PURPOSE"
    POLICY_CONCERN = "POLICY_CONCERN"                   # e.g. non-reimbursable item
    OTHER = "OTHER"


class TicketStatus(str, Enum):
    """Status of an expense ticket. Every expense line mirrors its ticket's status.
    APPROVED, AUTO_APPROVED and REJECTED are final and read-only."""
    PENDING = "PENDING"               # flagged, waiting for the manager
    AUTO_APPROVED = "AUTO_APPROVED"   # no flags, approved by rules at submission
    APPROVED = "APPROVED"             # manager approved
    REJECTED = "REJECTED"             # manager rejected (reason + comment required)


class TicketRouting(str, Enum):
    AUTO = "AUTO"         # zero flags on every line
    MANAGER = "MANAGER"   # at least one flag on any line


class ExpenseCategory(str, Enum):
    """The only five allowed expense types [POL-6.1]."""
    AIRFARE = "AIRFARE"
    LODGING = "LODGING"
    MEALS = "MEALS"
    GROUND_TRANSPORT = "GROUND_TRANSPORT"
    INCIDENTALS = "INCIDENTALS"


class PolicyRuleCode(str, Enum):
    """Deterministic policy flags [POL-9.1]. They route a ticket to the manager; they never
    block submission. (Things that DO block submission are validation errors, e.g. a
    missing receipt photo or an expense date before the trip was created.)"""
    OVER_THRESHOLD = "OVER_THRESHOLD"
    DUPLICATE_RECEIPT = "DUPLICATE_RECEIPT"


class WeatherStatus(str, Enum):
    """Result of one get_weather_forecast call."""
    AVAILABLE = "AVAILABLE"                       # every requested date has forecast values
    PARTIAL = "PARTIAL"                           # some dates covered, some not
    FORECAST_OUT_OF_RANGE = "FORECAST_OUT_OF_RANGE"  # no requested date inside the forecast range
    LOCATION_NOT_FOUND = "LOCATION_NOT_FOUND"
    LOCATION_AMBIGUOUS = "LOCATION_AMBIGUOUS"     # several big places share the name; ask the user
    ERROR = "ERROR"                               # timeout, HTTP error, invalid/empty response


class ChatSessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"       # user clicked X, or a new session replaced it
    EXPIRED = "EXPIRED"     # 60 minutes without a message


class SessionCloseReason(str, Enum):
    USER_CLOSED = "USER_CLOSED"
    IDLE_TIMEOUT = "IDLE_TIMEOUT"
    REPLACED = "REPLACED"   # employee opened a new chat while an old one was still ACTIVE


class ChatIntent(str, Enum):
    """Decided by chat/intent_router.py BEFORE the LLM is called. It controls which tool
    the LLM may use in this turn (RAG never runs for a weather-only message)."""
    POLICY = "POLICY"                         # expense policy / how to use TravelDesk -> RAG tool
    WEATHER = "WEATHER"                       # weather / packing / clothing -> weather tool
    POLICY_AND_WEATHER = "POLICY_AND_WEATHER" # both in one message -> both tools
    GREETING = "GREETING"                     # hello / thanks -> short reply, no tools
    OUT_OF_SCOPE = "OUT_OF_SCOPE"             # anything else (incl. "show my trips") -> boundary reply


class ConversationStatus(str, Enum):
    """One 'conversation' = one turn: human message -> (tool calls) -> final AI response."""
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"     # answered, but one tool failed (e.g. policy OK, weather timed out)
    BLOCKED = "BLOCKED"     # input guardrail stopped it before the LLM
    FAILED = "FAILED"       # LLM failure or every tool failed; a safe error reply was stored


class GuardrailStatus(str, Enum):
    PASSED = "PASSED"
    INPUT_BLOCKED = "INPUT_BLOCKED"          # prompt injection / abuse
    INPUT_REDACTED = "INPUT_REDACTED"        # personal data masked, then continued
    OUTPUT_REWRITTEN = "OUTPUT_REWRITTEN"    # ungrounded number / invalid citation / promise fixed


class MessageType(str, Enum):
    """Exact values stored in chat_messages.message_type."""
    HUMAN_MESSAGE = "human_message"
    AI_TOOL_CALL = "ai_tool_call"
    TOOL_RESPONSE = "tool_response"
    AI_RESPONSE = "ai_response"


class ToolName(str, Enum):
    """The ONLY two tools Vera has. Neither reads business tables."""
    SEARCH_EXPENSE_POLICY = "search_expense_policy"   # RAG over the expense policy
    GET_WEATHER_FORECAST = "get_weather_forecast"     # Open-Meteo, employee-supplied inputs


class AIProvider(str, Enum):
    OPENROUTER = "openrouter"   # Option A (team choice: nvidia/nemotron-3.5-super-vl:free)
    GEMINI = "gemini"           # Option A alternative
    AZURE = "azure"             # Option B


class AIFeature(str, Enum):
    CHAT = "CHAT"               # Vera answer generation (incl. tool-calling rounds)
    SUMMARY = "SUMMARY"         # rolling summary of older turns in the SAME session


class AICallStatus(str, Enum):
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"   # HTTP 429 / quota
    AUTH_ERROR = "AUTH_ERROR"       # HTTP 401/403, bad or missing key
    INVALID_OUTPUT = "INVALID_OUTPUT"
    ERROR = "ERROR"


class ErrorSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ErrorCategory(str, Enum):
    """error_logs.category: which kind of failure happened."""
    VALIDATION = "VALIDATION"
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    BUSINESS_RULE = "BUSINESS_RULE"
    API = "API"
    DATABASE = "DATABASE"
    RAG = "RAG"
    LLM = "LLM"
    WEATHER = "WEATHER"
    TIMEOUT = "TIMEOUT"
    PARSING = "PARSING"
    RATE_LIMIT = "RATE_LIMIT"
    UNEXPECTED = "UNEXPECTED"


class ErrorCode(str, Enum):
    """Stable, machine-readable codes in every error response and in error_logs.
    React maps them to friendly text; the HTTP status is in the comment."""
    # --- generic ---
    VALIDATION_ERROR = "VALIDATION_ERROR"                  # 422 (field errors in details)
    NOT_FOUND = "NOT_FOUND"                                # 404
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"              # 405 no edit/delete of decided records
    FORBIDDEN = "FORBIDDEN"                                # 403 wrong role (e.g. Manager calling chat)
    # A record that exists but belongs to someone else returns NOT_FOUND (404), so ids cannot be probed.
    INTERNAL_ERROR = "INTERNAL_ERROR"                      # 500
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"          # 503
    # --- authentication (JWT) ---
    UNAUTHENTICATED = "UNAUTHENTICATED"                    # 401 no Authorization header
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"            # 401 wrong e-mail or password (same text)
    TOKEN_EXPIRED = "TOKEN_EXPIRED"                        # 401 JWT past its exp
    INVALID_TOKEN = "INVALID_TOKEN"                        # 401 bad signature / malformed / unknown user
    # --- trips ---
    TRIP_NOT_EDITABLE = "TRIP_NOT_EDITABLE"                # 409 edit after the manager decided
    TRIP_NOT_ACTIVE = "TRIP_NOT_ACTIVE"                    # 409 ticket on In Progress / Rejected / Completed trip
    TRIP_NOT_FINISHED = "TRIP_NOT_FINISHED"                # 409 manager completes before end date
    TRIP_APPROVAL_WINDOW_PASSED = "TRIP_APPROVAL_WINDOW_PASSED"  # 409 approve after start + 90 days
    ALREADY_DECIDED = "ALREADY_DECIDED"                    # 409 second decision on the same record
    SELF_APPROVAL = "SELF_APPROVAL"                        # 403 deciding your own record
    # --- expenses / evidence ---
    EXPENSE_DATE_BEFORE_TRIP_CREATED = "EXPENSE_DATE_BEFORE_TRIP_CREATED"  # 422 [POL-8.2]
    EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"              # 404 unknown evidence_id or not the caller's
    EVIDENCE_ALREADY_USED = "EVIDENCE_ALREADY_USED"        # 409 photo already attached to another line
    EVIDENCE_INVALID_FILE = "EVIDENCE_INVALID_FILE"        # 415 not a real JPEG/PNG/WEBP
    EVIDENCE_TOO_LARGE = "EVIDENCE_TOO_LARGE"              # 413 bigger than EVIDENCE_MAX_BYTES
    REPLACEMENT_NOT_ALLOWED = "REPLACEMENT_NOT_ALLOWED"    # 409 replacement_of_ticket_id invalid / reused
    TICKET_READ_ONLY = "TICKET_READ_ONLY"                  # 409 any change to a decided ticket
    # --- chat (Vera) ---
    SESSION_EXPIRED = "SESSION_EXPIRED"                    # 410 idle > 60 min
    SESSION_CLOSED = "SESSION_CLOSED"                      # 410 closed with X / replaced
    CHAT_RATE_LIMITED = "CHAT_RATE_LIMITED"                # 429 too many messages per minute
    AI_UNAVAILABLE = "AI_UNAVAILABLE"                      # 503 LLM timeout / 5xx
    AI_RATE_LIMITED = "AI_RATE_LIMITED"                    # 429 provider quota
    AI_AUTH_ERROR = "AI_AUTH_ERROR"                        # 503 invalid key (details only in logs)
    POLICY_RETRIEVAL_FAILED = "POLICY_RETRIEVAL_FAILED"    # tool error: RAG unavailable
    # --- weather tool (returned inside ToolResult, shown by Vera, logged) ---
    WEATHER_INPUT_MISSING = "WEATHER_INPUT_MISSING"        # destination / start / end not given
    WEATHER_INVALID_DATES = "WEATHER_INVALID_DATES"        # end before start, span > 30 days, bad format
    FORECAST_OUT_OF_RANGE = "FORECAST_OUT_OF_RANGE"        # dates outside the provider's forecast range
    WEATHER_LOCATION_NOT_FOUND = "WEATHER_LOCATION_NOT_FOUND"
    WEATHER_LOCATION_AMBIGUOUS = "WEATHER_LOCATION_AMBIGUOUS"
    WEATHER_TIMEOUT = "WEATHER_TIMEOUT"
    WEATHER_CONNECTION_FAILED = "WEATHER_CONNECTION_FAILED"
    WEATHER_PROVIDER_ERROR = "WEATHER_PROVIDER_ERROR"      # HTTP 5xx from Open-Meteo
    WEATHER_RATE_LIMITED = "WEATHER_RATE_LIMITED"          # HTTP 429 from Open-Meteo
    WEATHER_INVALID_RESPONSE = "WEATHER_INVALID_RESPONSE"  # invalid JSON / parsing failure
    WEATHER_EMPTY_RESPONSE = "WEATHER_EMPTY_RESPONSE"
    WEATHER_UNEXPECTED_ERROR = "WEATHER_UNEXPECTED_ERROR"


# =============================================================================
# 2. BASE MODELS
# =============================================================================
class InModel(BaseModel):
    """Base for request bodies: trims spaces on every string and rejects unknown fields,
    so a typo like 'destinaton' is a 422 instead of being silently ignored."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class OutModel(BaseModel):
    """Base for responses and internal DTOs. from_attributes=True lets us build a model
    straight from a SQLAlchemy Row (row._mapping) or any object with matching attributes."""
    model_config = ConfigDict(from_attributes=True)


def _check_review_comment(decision: Decision, comment: str | None) -> None:
    """Shared rule for trip and ticket decisions: a rejection must explain itself."""
    if decision == Decision.REJECTED and len((comment or "").strip()) < MIN_REVIEW_COMMENT_CHARS:
        raise ValueError(f"review_comment of at least {MIN_REVIEW_COMMENT_CHARS} characters is required to reject")


# =============================================================================
# 3. COMMON: error envelope and health
# =============================================================================
class ErrorBody(OutModel):
    code: ErrorCode
    message: str                                   # safe, user-facing sentence
    details: list[dict[str, Any]] | None = None    # e.g. [{"field": "expenses.0.expense_date", "msg": "..."}]
    request_id: str | None = None                  # ties the UI error to backend logs
    correlation_id: str | None = None              # same id across request -> session -> tool -> LLM
    retryable: bool = False                        # UI shows a Retry button when True


class ErrorResponse(OutModel):
    """Every non-2xx response has exactly this shape: {"error": {...}}"""
    error: ErrorBody


class DependencyHealth(OutModel):
    name: Literal["database", "weather_api", "ai_provider", "policy_index", "scheduler"]
    ok: bool
    latency_ms: int | None = None
    detail: str | None = None


class HealthOut(OutModel):
    status: Literal["ok", "degraded", "down"]      # degraded = DB ok, weather/AI not
    dependencies: list[DependencyHealth]
    checked_at: datetime


# =============================================================================
# 4. AUTH (JWT) / EMPLOYEES / CURRENT USER
#    POST /auth/login -> TokenOut. React keeps access_token in sessionStorage and sends
#    "Authorization: Bearer <token>". core/security.py signs/decodes (HS256, PyJWT) and
#    hashes passwords (bcrypt). The role is ALWAYS re-read from the database on every
#    request; the role claim only helps React choose the view.
# =============================================================================
class LoginRequest(InModel):
    """POST /api/v1/auth/login"""
    email: str = Field(..., max_length=254, examples=["rohan.mehta@veridian.example"])
    password: str = Field(..., min_length=MIN_PASSWORD_CHARS, max_length=MAX_PASSWORD_CHARS)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        if not EMAIL_PATTERN.fullmatch(v):
            raise ValueError("Enter a valid email address")
        return v.lower()                                   # e-mails are stored lower-case


class TokenPayload(BaseModel):
    """Claims inside the JWT. A JWT is signed, not encrypted: no personal data or secrets here."""
    sub: str                       # employee_id as a string (JWT standard: 'sub' is a string)
    role: Role                     # selects the React view; backend re-checks it in the database
    iat: int                       # issued-at (unix seconds)
    exp: int                       # expiry = iat + JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @property
    def employee_id(self) -> int:
        return int(self.sub)


class EmployeeOut(OutModel):
    """Never contains password_hash."""
    employee_id: int
    full_name: str
    email: str
    department: str
    role: Role
    manager_id: int | None = None


class TokenOut(OutModel):
    """Response of POST /auth/login. No refresh token in this scope: after expiry, log in again."""
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int                # seconds
    user: EmployeeOut              # lets React show the name and pick the view straight away


class CurrentUser(EmployeeOut):
    """Injected by Depends(get_current_user): verified JWT + fresh database read.
    Services receive this object, never a raw id from the request body."""

    @property
    def is_manager(self) -> bool:
        return self.role == Role.MANAGER


# =============================================================================
# 5. TRIPS (travel requests)
# =============================================================================
class TripBase(InModel):
    """Fields shared by create and update. Validators = [POL-3.2]..[POL-3.4]."""
    destination: str = Field(..., min_length=2, max_length=100, examples=["Bengaluru"])
    start_date: date = Field(..., examples=["2026-11-25"])
    end_date: date = Field(..., examples=["2026-11-28"])
    purpose: str = Field(..., min_length=MIN_PURPOSE_CHARS, max_length=MAX_PURPOSE_CHARS,
                         examples=["Client workshop for FY27 audit planning"])

    @field_validator("destination")
    @classmethod
    def clean_destination(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v)                       # collapse double spaces
        if not DESTINATION_PATTERN.fullmatch(v):
            raise ValueError("Destination must be a city name using letters, spaces and . , ' ( ) -")
        return v

    @model_validator(mode="after")
    def check_dates(self) -> "TripBase":
        t = today()
        if self.start_date < t:
            raise ValueError("start_date must be today or a future date")
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be later than start_date")
        if (self.end_date - self.start_date).days + 1 > MAX_TRIP_DAYS:
            raise ValueError(f"A trip can last at most {MAX_TRIP_DAYS} days")
        if self.start_date > t + timedelta(days=MAX_DAYS_IN_ADVANCE):
            raise ValueError("A trip cannot start more than one year from today")
        return self


class TripCreate(TripBase):
    """POST /api/v1/trips (Employee). employee_id comes from the JWT, not the body."""


class TripUpdate(TripBase):
    """PUT /api/v1/trips/{trip_id} (owner). Full replacement, only while IN_PROGRESS."""


class TripDecisionRequest(InModel):
    """POST /api/v1/trips/{trip_id}/decision (Manager)."""
    decision: Decision
    review_comment: str | None = Field(None, max_length=MAX_REVIEW_COMMENT_CHARS)

    @model_validator(mode="after")
    def reject_needs_comment(self) -> "TripDecisionRequest":
        _check_review_comment(self.decision, self.review_comment)
        return self


class TripApprovalOut(OutModel):
    """One row of trip_approvals (decision history, never overwritten)."""
    approval_id: int
    trip_id: int
    reviewer_id: int
    reviewer_name: str
    decision: Decision
    review_comment: str | None
    decided_at: datetime


def _check_trip_status_pair(approval_status: ApprovalStatus, trip_state: TripState | None) -> None:
    """Same rule as the DB CHECK: trip_state is set ONLY for approved trips."""
    if (approval_status == ApprovalStatus.APPROVED) != (trip_state is not None):
        raise ValueError("trip_state must be ACTIVE/COMPLETED for APPROVED trips and null otherwise")


class TripOut(OutModel):
    trip_id: int
    trip_code: str                       # "TRP-00012" (generated column)
    employee_id: int
    employee_name: str
    department: str
    destination: str
    start_date: date
    end_date: date
    purpose: str
    approval_status: ApprovalStatus
    trip_state: TripState | None         # None unless APPROVED
    status_label: str                    # "In Progress" | "Rejected" | "Approved - Active" | "Approved - Completed"
    created_on: date                     # date the trip id was created
    earliest_expense_date: date          # = created_on: expenses dated earlier are rejected [POL-8.2]
    auto_complete_on: date               # = start_date + 90 days [POL-4.3]
    completion_type: CompletionType | None = None
    completed_by_name: str | None = None # manager name (None when AUTO)
    completed_at: datetime | None = None
    # UI hints computed for the CALLER (the backend re-checks every action anyway):
    can_edit: bool                       # owner and IN_PROGRESS
    can_raise_ticket: bool               # owner and APPROVED + ACTIVE
    can_decide: bool                     # approving manager and IN_PROGRESS and within the approval window
    can_complete: bool                   # approving manager, ACTIVE and today >= end_date
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def status_pair_is_valid(self) -> "TripOut":
        _check_trip_status_pair(self.approval_status, self.trip_state)
        return self


class TripListItemOut(OutModel):
    """Card on My Trips, and rows of the manager's Trip requests / Trips to complete lists."""
    trip_id: int
    trip_code: str
    employee_name: str
    destination: str
    start_date: date
    end_date: date
    approval_status: ApprovalStatus
    trip_state: TripState | None
    status_label: str
    auto_complete_on: date
    ticket_count: int = 0
    pending_ticket_count: int = 0
    total_claimed: MoneyOut = Decimal("0")

    @model_validator(mode="after")
    def status_pair_is_valid(self) -> "TripListItemOut":
        _check_trip_status_pair(self.approval_status, self.trip_state)
        return self


class TripDetailOut(TripOut):
    """GET /api/v1/trips/{trip_id}: trip + decision history + its tickets."""
    approvals: list[TripApprovalOut] = []
    tickets: list["TicketSummaryOut"] = []


# =============================================================================
# 6. EVIDENCE (receipt photos), stored locally inside PostgreSQL
#    Step 1: React uploads each photo: POST /api/v1/evidence (multipart, field "file")
#            -> EvidenceUploadOut (metadata in expense_evidence, bytes in evidence_files).
#    Step 2: React submits the ticket as JSON with one evidence_id per line.
#    Viewing: GET /api/v1/evidence/{evidence_id}/file streams the image after a JWT
#             ownership / approver check (React fetches it with the token -> blob URL).
# =============================================================================
class EvidenceUploadOut(OutModel):
    evidence_id: UUID                      # unique, never reused
    evidence_code: str                     # "EVD-00026" (display id)
    original_filename: str
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int
    sha256: str                            # duplicate-photo check
    uploaded_at: datetime


# =============================================================================
# 7. EXPENSE TICKETS, EXPENSE LINES, POLICY FLAGS, DECISIONS
# =============================================================================
class ExpenseLineCreate(InModel):
    """One expense line inside POST /api/v1/trips/{trip_id}/tickets.
    TicketService also checks expense_date >= the trip's creation date
    (422 EXPENSE_DATE_BEFORE_TRIP_CREATED, reported on field expenses.<i>.expense_date)."""
    expense_type: ExpenseCategory
    amount: Decimal = Field(..., gt=0, le=MAX_LINE_AMOUNT_INR, max_digits=12, decimal_places=2,
                            examples=["1850.00"])
    expense_date: date
    description: str = Field(..., min_length=3, max_length=300)
    evidence_id: UUID                      # REQUIRED receipt photo [POL-7.1]; missing -> 422
    invoice_number: str | None = Field(None, max_length=50, examples=["INV-88231"])   # optional

    @field_validator("expense_date")
    @classmethod
    def not_in_future(cls, v: date) -> date:
        if v > today():                                   # [POL-8.1]
            raise ValueError("expense_date cannot be in the future")
        return v

    @field_validator("invoice_number", mode="before")
    @classmethod
    def blank_invoice_is_none(cls, v: Any) -> Any:
        # "" or "   " from the optional form field means "no invoice number given"
        return None if v is None or (isinstance(v, str) and not v.strip()) else v

    @field_validator("invoice_number")
    @classmethod
    def invoice_format(cls, v: str | None) -> str | None:
        if v is not None and not INVOICE_PATTERN.fullmatch(v):
            raise ValueError("Invoice number: 3-50 letters, numbers, - _ or /")
        return v.upper() if v else v                      # normalised for the duplicate check


class TicketCreate(InModel):
    """POST /api/v1/trips/{trip_id}/tickets. trip_id comes from the URL path.
    A correction after a rejection is just a NEW ticket on the same trip; the optional
    replacement_of_ticket_id only records which rejected ticket it replaces."""
    expenses: list[ExpenseLineCreate] = Field(..., min_length=MIN_LINES_PER_TICKET,
                                              max_length=MAX_LINES_PER_TICKET)
    replacement_of_ticket_id: int | None = None

    @model_validator(mode="after")
    def no_duplicates_inside_ticket(self) -> "TicketCreate":
        photos = [e.evidence_id for e in self.expenses]
        if len(photos) != len(set(photos)):
            raise ValueError("Each expense line needs its own receipt photo")
        invoices = [e.invoice_number for e in self.expenses if e.invoice_number]
        if len(invoices) != len(set(invoices)):
            raise ValueError("The same invoice number appears twice in this ticket")
        return self


class PolicyFlag(OutModel):
    """Produced by services/policy_engine.py (pure function: no DB, no AI)."""
    rule_code: PolicyRuleCode
    message: str                           # "MEALS amount 1,800.00 is above the 1,500.00 review threshold"
    policy_ref: str                        # "[POL-6.2]"
    threshold_amount: MoneyOut | None = None


class PolicyCheckOut(OutModel):
    """GET /api/v1/expenses/{expense_id}/policy-check (re-runs the rules, read-only)."""
    expense_id: int
    expense_code: str
    flags: list[PolicyFlag]
    requires_manager_review: bool
    rules_version: str                     # e.g. "VGS-FIN-TE-001 v2.0"


class ExpenseOut(OutModel):
    expense_id: int
    expense_code: str                      # "EXP-00031"
    ticket_id: int
    trip_id: int
    expense_type: ExpenseCategory
    amount: MoneyOut
    currency: Literal["INR"] = "INR"
    expense_date: date
    description: str
    evidence_id: UUID                      # image via GET /evidence/{evidence_id}/file
    evidence_code: str                     # "EVD-00012"
    invoice_number: str | None
    status: TicketStatus                   # mirrors the ticket
    flags: list[PolicyFlag] = []
    created_at: datetime


class TicketDecisionRequest(InModel):
    """POST /api/v1/tickets/{ticket_id}/decision (Manager; ticket must be PENDING).
    Rejection needs BOTH a reason category and a written review comment."""
    decision: Decision
    rejection_reason: RejectionReason | None = None
    review_comment: str | None = Field(None, max_length=MAX_REVIEW_COMMENT_CHARS)

    @model_validator(mode="after")
    def rejection_rules(self) -> "TicketDecisionRequest":
        _check_review_comment(self.decision, self.review_comment)
        if self.decision == Decision.REJECTED and self.rejection_reason is None:
            raise ValueError("rejection_reason is required to reject a ticket")
        if self.decision == Decision.APPROVED and self.rejection_reason is not None:
            raise ValueError("rejection_reason is only allowed when rejecting")
        return self


class TicketApprovalOut(OutModel):
    """One row of ticket_approvals (includes SYSTEM auto-approvals). Immutable."""
    approval_id: int
    ticket_id: int
    reviewer_type: ReviewerType
    reviewer_id: int | None                # None when reviewer_type = SYSTEM
    reviewer_name: str                     # "SYSTEM" for auto-approval
    decision: TicketDecisionValue
    rejection_reason: RejectionReason | None
    review_comment: str | None
    decided_at: datetime


class TicketSummaryOut(OutModel):
    """Row in ticket lists (Trip Detail, Expense Management, manager queue)."""
    ticket_id: int
    ticket_code: str                       # "TKT-00007"
    trip_id: int
    trip_code: str
    status: TicketStatus
    routing: TicketRouting
    line_count: int
    flag_count: int
    total_amount: MoneyOut
    submitted_at: datetime
    decided_at: datetime | None
    is_read_only: bool                     # True once decided (always True except PENDING)
    replacement_of_ticket_code: str | None = None   # this ticket replaces ...
    replaced_by_ticket_code: str | None = None      # this rejected ticket was replaced by ...


class TicketDetailOut(TicketSummaryOut):
    """GET /api/v1/tickets/{ticket_id} and the response of ticket creation."""
    destination: str
    employee_id: int
    employee_name: str
    expenses: list[ExpenseOut]
    history: list[TicketApprovalOut]
    can_create_replacement: bool           # REJECTED, not yet replaced, trip still ACTIVE, caller is owner


class PendingTicketOut(TicketSummaryOut):
    """GET /api/v1/tickets/pending: manager queue (direct reports only)."""
    destination: str
    employee_name: str
    flag_codes: list[PolicyRuleCode]


class PendingExpenseOut(OutModel):
    """GET /api/v1/expenses/pending: flagged LINES inside pending tickets."""
    expense_id: int
    expense_code: str
    ticket_code: str
    trip_code: str
    employee_name: str
    destination: str
    expense_type: ExpenseCategory
    amount: MoneyOut
    flag_codes: list[PolicyRuleCode]
    submitted_at: datetime


# =============================================================================
# 8. REPORTS (manager Spending Summary — the three required SQL demonstrations)
# =============================================================================
class TripExpenseJoinRow(OutModel):
    """SQL demo 1: JOIN employees + trips + expenses."""
    employee_name: str
    trip_code: str
    destination: str
    expense_code: str
    expense_type: ExpenseCategory
    amount: MoneyOut
    status: TicketStatus


class SpendByTripCategoryRow(OutModel):
    """SQL demo 2: SUM / COUNT by trip and category (approved + auto-approved only)."""
    trip_code: str
    destination: str
    expense_type: ExpenseCategory | None   # None = trip total row (GROUPING SETS)
    line_count: int
    total_amount: MoneyOut


class PolicyRulesOut(OutModel):
    """GET /api/v1/policy/rules: lets React show limits next to the form."""
    rules_version: str
    review_thresholds_inr: dict[ExpenseCategory, MoneyOut]
    hard_cap_per_line_inr: MoneyOut
    evidence_required: bool = True
    evidence_max_bytes: int
    evidence_mime_types: list[str] = list(ALLOWED_EVIDENCE_MIME_TYPES)
    trip_auto_complete_days_after_start: int
    max_days_in_advance: int = MAX_DAYS_IN_ADVANCE
    max_lines_per_ticket: int = MAX_LINES_PER_TICKET


# =============================================================================
# 9. VERA — weather data shapes (tool output + structured weather answer)
# =============================================================================
class DailyForecast(OutModel):
    """One day from Open-Meteo, values copied EXACTLY from the API (None = not returned).
    Only these fields exist; nothing else (e.g. UV) is requested or used."""
    date: date
    weather_code: int | None = None                        # WMO code
    condition: str | None = None                           # text mapped in code from weather_code
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    precipitation_probability_max_pct: int | None = None
    precipitation_sum_mm: float | None = None
    wind_speed_max_kmh: float | None = None


class WeatherForecastResult(OutModel):
    """Data part of the get_weather_forecast ToolResult. Logged in weather_tool_logs."""
    status: WeatherStatus
    destination: str                       # exactly as the employee wrote it
    resolved_location: str | None = None   # "Bengaluru, Karnataka, India"
    latitude: float | None = None
    longitude: float | None = None
    requested_from: date
    requested_to: date
    covered_dates: list[date] = []         # dates WITH forecast values
    uncovered_dates: list[date] = []       # dates outside the forecast range ("Forecast not available")
    days: list[DailyForecast] = []
    candidates: list[str] = []             # filled only for LOCATION_AMBIGUOUS
    source: str = "Open-Meteo"
    retrieved_at: datetime
    from_cache: bool = False


class ForecastBasis(OutModel):
    """Built by CODE from WeatherForecastResult, never by the LLM."""
    source: str
    resolved_location: str | None
    date_from: date
    date_to: date
    forecast_available: bool
    coverage: Literal["FULL", "PARTIAL", "NONE"]
    covered_dates: list[date] = []
    uncovered_dates: list[date] = []
    retrieved_at: datetime | None = None


class VeraWeatherLLMOutput(BaseModel):
    """The ONLY weather fields the LLM writes (structured output). ai/output_validators.py
    checks every number and condition against the tool result before it is shown."""
    model_config = ConfigDict(extra="ignore")
    weather_summary: str = Field(..., max_length=700)
    travel_checklist: list[str] = Field(..., min_length=3, max_length=5)
    limitations: list[str] = Field(..., min_length=1, max_length=5)

    @field_validator("travel_checklist", "limitations")
    @classmethod
    def no_empty_items(cls, items: list[str]) -> list[str]:
        cleaned = [i.strip() for i in items if i and i.strip()]
        if len(cleaned) != len(items):
            raise ValueError("List items cannot be empty")
        return cleaned


class VeraWeatherAnswer(OutModel):
    """Weather part of a Vera reply. Keeps the brief's five AI output fields
    (destination, forecast_basis, weather_summary, travel_checklist, limitations).
    Stored in chat_messages.metadata of the ai_response; shown as a card inside the chat."""
    destination: str
    forecast_basis: ForecastBasis
    weather_summary: str
    travel_checklist: list[str]
    limitations: list[str]
    disclaimer: str = ("Weather guidance is informational only. It is not an approval, a booking "
                       "or a safety guarantee.")


# =============================================================================
# 10. VERA — chat API contract (Employee role only; Managers get 403)
# =============================================================================
class ChatSessionOut(OutModel):
    """POST /api/v1/chat/sessions -> new ACTIVE session + intro message."""
    session_id: UUID
    status: ChatSessionStatus
    intro_message: str = ("Hi, I'm Vera, Veridian Global's travel assistant. I can explain our expense "
                          "policy and how to use TravelDesk, and check the weather for a destination "
                          "and dates you give me.")
    idle_timeout_minutes: int
    started_at: datetime


class ChatSessionListItemOut(OutModel):
    """GET /api/v1/chat/sessions: the caller's own chats, newest first (read-only history)."""
    session_id: UUID
    status: ChatSessionStatus
    close_reason: SessionCloseReason | None
    started_at: datetime
    last_activity_at: datetime
    closed_at: datetime | None
    turn_count: int
    preview: str                           # first employee message, cut to 80 characters


class ChatMessageRequest(InModel):
    """POST /api/v1/chat/sessions/{session_id}/messages. Text only: Vera receives no trip,
    ticket or expense ids from the UI."""
    message: str = Field(..., min_length=1, max_length=MAX_CHAT_MESSAGE_CHARS)


class Citation(OutModel):
    """A policy chunk the answer relied on, shown under the reply as e.g. [POL-6.2]."""
    ref_id: str                            # "POL-6.2", "GUIDE-6", "FAQ-1"
    title: str
    similarity: float


class ToolTrace(OutModel):
    """Summary of a tool call so the UI can show 'Checked the weather for Bengaluru'."""
    tool_name: ToolName
    status: Literal["ok", "error"]
    error_code: ErrorCode | None = None
    latency_ms: int


class ChatReplyOut(OutModel):
    session_id: UUID
    conversation_id: UUID
    turn_number: int
    intent: ChatIntent
    reply: str                             # plain text shown in the bubble
    citations: list[Citation] = []
    weather: VeraWeatherAnswer | None = None
    tools_used: list[ToolTrace] = []
    guardrail_status: GuardrailStatus
    status: ConversationStatus
    error_code: ErrorCode | None = None    # set when status is PARTIAL / FAILED
    retryable: bool = False
    created_at: datetime


class ChatMessageOut(OutModel):
    """One stored row of chat_messages (history and audit)."""
    message_id: int
    session_id: UUID
    conversation_id: UUID
    turn_number: int
    sequence_no: int
    message_type: MessageType
    content: str                           # personal data already masked
    tool_name: ToolName | None = None
    tool_call_id: str | None = None
    tool_args: dict[str, Any] | None = None   # sanitized
    metadata: dict[str, Any] | None = None    # citations, weather card, latency, error code
    created_at: datetime


class ChatHistoryOut(OutModel):
    session_id: UUID
    status: ChatSessionStatus
    read_only: bool                        # True for CLOSED / EXPIRED sessions
    messages: list[ChatMessageOut]


class ChatSessionCloseOut(OutModel):
    session_id: UUID
    status: ChatSessionStatus
    close_reason: SessionCloseReason
    closed_at: datetime


# =============================================================================
# 11. VERA — tool input schemas (LangChain @tool(args_schema=...)) and tool result
#     The LLM fills these from what the employee wrote in THIS session. There is no
#     trip_id / ticket_id / employee_id argument anywhere: Vera cannot reach business data.
# =============================================================================
class SearchPolicyInput(BaseModel):
    query: str = Field(..., min_length=3, max_length=300,
                       description="The expense-policy or TravelDesk how-to question to look up")


class WeatherToolInput(BaseModel):
    """All three fields are required. If the employee has not given them, Vera asks first;
    if the LLM still calls the tool without them, validation fails with
    WEATHER_INPUT_MISSING / WEATHER_INVALID_DATES and the provider is NOT called."""
    destination: str = Field(..., min_length=2, max_length=100,
                             description="City as written by the employee, e.g. 'Bengaluru' or 'Hyderabad, India'")
    start_date: date = Field(..., description="First day, ISO format YYYY-MM-DD")
    end_date: date = Field(..., description="Last day, ISO format YYYY-MM-DD (same as start for one day)")

    @field_validator("destination")
    @classmethod
    def clean_destination(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v.strip())
        if not DESTINATION_PATTERN.fullmatch(v):
            raise ValueError("destination must be a place name")
        return v

    @model_validator(mode="after")
    def check_range(self) -> "WeatherToolInput":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days + 1 > WEATHER_MAX_SPAN_DAYS:
            raise ValueError(f"At most {WEATHER_MAX_SPAN_DAYS} days per weather request")
        return self


class ToolResult(BaseModel):
    """Every tool returns this JSON, so the LLM always gets the same shape, even on errors.
    On error Vera states that the data is unavailable; it never guesses."""
    ok: bool
    data: dict[str, Any] | list[Any] | None = None
    error_code: ErrorCode | None = None
    error_message: str | None = None       # safe text, no internals
    retryable: bool = False


# =============================================================================
# 12. INTERNAL DTOs (passed between services; never returned directly to React)
# =============================================================================
class ToolContext(BaseModel):
    """Server-side context bound to the tools for one turn (invisible to the LLM).
    employee_id is used ONLY for chat ownership and logging, never to read business data."""
    employee_id: int
    session_id: UUID
    conversation_id: UUID
    correlation_id: str


class IntentDecision(BaseModel):
    """Output of chat/intent_router.py."""
    intent: ChatIntent
    allowed_tools: list[ToolName]          # tools the LLM may call in this turn
    reason: str                            # e.g. "keywords: rain, pack" or "inherited from turn 3"


class RetrievedChunk(BaseModel):
    """Row from policy_chunks returned by rag/retriever.py."""
    chunk_id: int
    ref_id: str                            # "POL-6.2"
    section_title: str
    content: str
    similarity: float                      # cosine similarity 0..1


class GuardrailResult(BaseModel):
    """Output of chat/guardrails.py input and output checks."""
    status: GuardrailStatus
    sanitized_text: str
    reasons: list[str] = []                # e.g. ["pii:phone", "injection:ignore_previous"]
    blocked_reply: str | None = None       # fixed safe reply when INPUT_BLOCKED


class ContextBundle(BaseModel):
    """What chat/context_builder.py assembles before each LLM call (CURRENT session only)."""
    system_prompt: str
    session_summary: str | None = None     # rolling summary of this session's older turns
    history: list[dict[str, Any]] = []     # recent turns of this session as LangChain messages
    user_message: str
    allowed_tools: list[ToolName] = []
    estimated_tokens: int = 0


class AICallLog(BaseModel):
    """Row for ai_call_logs (every LLM call). No prompts, keys or personal data."""
    feature: AIFeature
    provider: AIProvider
    model_name: str
    prompt_version: str                    # e.g. "vera-system-v2.0"
    status: AICallStatus
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error_code: str | None = None
    session_id: UUID | None = None
    conversation_id: UUID | None = None
    correlation_id: str


class RagCallLog(BaseModel):
    """Row for rag_call_logs (every policy retrieval)."""
    session_id: UUID
    conversation_id: UUID
    correlation_id: str
    query_text: str                        # masked, cut to 300 characters
    top_k: int
    retrieved_ref_ids: list[str] = []
    retrieval_scores: list[float] = []
    citations_used: list[str] = []         # filled after the answer is validated
    status: Literal["SUCCESS", "NO_MATCH", "FAILED"]
    error_code: ErrorCode | None = None
    latency_ms: int


class WeatherToolLog(BaseModel):
    """Row for weather_tool_logs (every get_weather_forecast call, success or failure).
    No trip or employee business record is linked."""
    session_id: UUID
    conversation_id: UUID
    correlation_id: str
    tool_call_id: str | None
    destination_query: str                 # sanitized text the employee gave
    start_date: date | None
    end_date: date | None
    resolved_location: str | None = None
    provider: str = "Open-Meteo"
    http_status: int | None = None
    result_status: WeatherStatus | None = None
    error_code: ErrorCode | None = None
    latency_ms: int
    cache_hit: bool = False
    retrieved_at: datetime | None = None


class ErrorLogRecord(BaseModel):
    """Row for error_logs (central error storage). Secrets are never put in here."""
    severity: ErrorSeverity
    source_component: str                  # e.g. "chat.weather_tool", "tickets.router"
    category: ErrorCategory
    error_code: ErrorCode
    safe_message: str                      # what the user saw
    internal_message: str                  # diagnostic text (no secrets, no tokens)
    http_status: int | None = None
    retryable: bool = False
    request_id: str | None = None
    correlation_id: str | None = None
    employee_id: int | None = None
    session_id: UUID | None = None
    conversation_id: UUID | None = None
    message_id: int | None = None
    tool_call_id: str | None = None
    context: dict[str, Any] | None = None  # sanitized key facts (never passwords/tokens/keys)
    stack_trace: str | None = None


# Resolve forward references used before their class was defined.
TripDetailOut.model_rebuild()

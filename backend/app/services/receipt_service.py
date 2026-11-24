"""
Receipt verification: read each photo once (vision model + Sightengine), then compare with the line.

Owner: Mradul (M3)  |  Spec: Agile Spec v2.1 > Receipt verification

* analyze(): the ONLY place that calls the AI for receipts. One reading per photo, stored in
  receipt_checks. A failed reading (AI down) is retried on the next request; a photo already
  attached to a line is never re-read (its result is frozen with the ticket).
* verify_for_form(): POST /evidence/{id}/verify - live result under each photo on the expense page.
* verify_line(): used by TicketService at submission (the authoritative check).
The comparison itself is plain code in receipt_rules.py.
"""
import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy.engine import Connection

from app.ai import llm_client, receipt_reader, sightengine_client
from app.core.config import get_settings
from app.core.errors import AppError
from app.repositories import evidence_repo, receipt_repo, trip_repo
from app.schemas import (
    CurrentUser,
    ErrorCode,
    ExpenseCategory,
    ReceiptReadingOut,
    ReceiptReadStatus,
    ReceiptVerdict,
    ReceiptVerificationOut,
    ReceiptVerifyRequest,
)
from app.services import policy_engine, receipt_rules, trip_service

log = logging.getLogger(__name__)

OUTCOMES = {
    (ReceiptVerdict.VALID, False): "Receipt verified.",
    (ReceiptVerdict.VALID, True): "Receipt verified. Your manager will see the receipt summary with this line.",
    (ReceiptVerdict.INVALID, False): "This receipt doesn't match the line. The line will go to your manager for review.",
    (ReceiptVerdict.INVALID, True): (
        "This receipt doesn't match the line. Above the review threshold, the line will be rejected "
        "automatically when you submit. Correct the line or upload the right receipt."
    ),
    (ReceiptVerdict.UNREADABLE, False): "We couldn't read this receipt. Upload a clearer photo of the whole receipt.",
    (ReceiptVerdict.NOT_VERIFIED, False): "The receipt couldn't be checked right now. Your manager will review this line.",
    (ReceiptVerdict.INCOMPLETE, False): "Enter the category, amount and date to finish the check.",
}


def enabled() -> bool:
    return get_settings().receipt_check_enabled


def outcome(verdict: ReceiptVerdict, over_threshold: bool) -> str:
    return OUTCOMES.get((verdict, over_threshold)) or OUTCOMES[(verdict, False)]


def to_reading(row: dict | None) -> receipt_rules.Reading | None:
    if row is None:
        return None
    return receipt_rules.Reading(
        status=ReceiptReadStatus(row["status"]),
        is_receipt=row["is_receipt"],
        total_amount=row["total_amount"],
        receipt_date=row["receipt_date"],
        city=row["city"],
        from_place=row["from_place"],
        to_place=row["to_place"],
        ai_generated_score=row["ai_generated_score"],
    )


def _run_ai(content: bytes, mime_type: str) -> dict:
    """Call Sightengine and the vision model. Never raises: failures become status ERROR."""
    reading: dict = {
        "status": ReceiptReadStatus.ERROR.value, "is_receipt": None, "total_amount": None, "currency": None,
        "receipt_date": None, "merchant": None, "city": None, "from_place": None, "to_place": None,
        "summary": None, "ai_generated_score": None, "error_code": None, "model_name": receipt_reader.model_name(),
    }
    try:
        reading["ai_generated_score"] = sightengine_client.ai_generated_score(content, mime_type)
    except sightengine_client.SightengineError as exc:
        reading["error_code"] = exc.code            # authenticity NOT_CHECKED; reading continues
        log.warning("sightengine failed: %s", exc.code)

    try:
        output = receipt_reader.read_receipt(content, mime_type)
    except llm_client.LLMError as exc:
        reading["error_code"] = exc.code.value if hasattr(exc.code, "value") else str(exc.code)
        return reading
    if output is None:
        reading["error_code"] = "AI_INVALID_OUTPUT"
        return reading

    reading.update(output.model_dump(include={
        "is_receipt", "total_amount", "currency", "receipt_date", "merchant",
        "city", "from_place", "to_place", "summary",
    }))
    readable = output.is_receipt and output.readable
    reading["status"] = (ReceiptReadStatus.READ if readable else ReceiptReadStatus.UNREADABLE).value
    return reading


def analyze(db: Connection, employee: CurrentUser, evidence_id: UUID) -> dict:
    """Reading of the caller's own photo: stored one, or a new AI reading (also when the last one failed)."""
    photo = evidence_repo.get_file(db, evidence_id)
    if photo is None or photo["employee_id"] != employee.employee_id:
        raise AppError(ErrorCode.EVIDENCE_NOT_FOUND, 404, "Receipt photo not found.")
    stored = receipt_repo.get(db, evidence_id)
    if stored is not None and (stored["status"] != ReceiptReadStatus.ERROR.value
                               or receipt_repo.is_attached(db, evidence_id)):
        return stored
    reading = _run_ai(bytes(photo["content"]), photo["mime_type"])
    row = receipt_repo.upsert(db, {"evidence_id": evidence_id, **reading})
    db.commit()
    return row


def _threshold(expense_type: ExpenseCategory | None) -> Decimal | None:
    if expense_type is None:
        return None
    config = policy_engine.PolicyConfig.from_settings(get_settings())
    return config.thresholds[ExpenseCategory(expense_type)]


def verify_line(
    reading_row: dict | None,
    expense_type: ExpenseCategory | None,
    amount: Decimal | None,
    expense_date,
    trip: dict,
) -> receipt_rules.Verification:
    """Compare one stored reading with one line (pure; used by the form and by submission)."""
    return receipt_rules.verify(
        to_reading(reading_row),
        receipt_rules.LineFacts(expense_type, amount, expense_date),
        receipt_rules.TripFacts(trip["destination"], trip["created_on"]),
        receipt_rules.RuleConfig.from_settings(get_settings()),
    )


def verify_for_form(
    db: Connection, employee: CurrentUser, evidence_id: UUID, request: ReceiptVerifyRequest
) -> ReceiptVerificationOut:
    """POST /evidence/{id}/verify: read the photo if needed, compare with the line as typed so far."""
    if not enabled():
        return ReceiptVerificationOut(
            evidence_id=evidence_id, verdict=ReceiptVerdict.NOT_VERIFIED,
            outcome="Receipt checking is switched off.", enabled=False,
        )
    trip = trip_repo.get(db, request.trip_id)
    if trip is None or not trip_service.is_owner(employee, trip):
        raise AppError(ErrorCode.NOT_FOUND, 404, "Trip not found.")
    row = analyze(db, employee, evidence_id)
    result = verify_line(row, request.expense_type, request.amount, request.expense_date, trip)
    threshold = _threshold(request.expense_type)
    over = threshold is not None and request.amount is not None and request.amount > threshold
    return ReceiptVerificationOut(
        evidence_id=evidence_id,
        verdict=result.verdict,
        checks=result.checks,
        reading=ReceiptReadingOut(**row),
        over_threshold=over,
        outcome=outcome(result.verdict, over),
    )

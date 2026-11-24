"""
Pure functions: compare what was READ from a receipt with the expense line the employee typed.

Owner: Mradul (M3)  |  Spec: Agile Spec v2.1 > Receipt verification

"Pure" like policy_engine.py: no database, no AI, no clock. The AI only reads the receipt once
(services/receipt_service.py); every decision below is plain, repeatable code.

Checks (each PASS / FAIL / NOT_ON_RECEIPT / MISSING_INPUT / NOT_CHECKED):
  AMOUNT        receipt total vs amount typed, tolerance max(1 %, Rs 10)
  DATE          receipt date within 1 day of the expense date, and not before the trip was created
  PLACE         city / route on the receipt matches the trip destination (not printed = not a failure)
  AUTHENTICITY  Sightengine AI-generated score below 0.5

Verdict: any FAIL -> INVALID; else a value not typed yet -> INCOMPLETE; else VALID.
Unreadable photo -> UNREADABLE (blocks submission). AI failure -> NOT_VERIFIED (manager reviews).
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.schemas import (
    ExpenseCategory,
    ReceiptCheckItem,
    ReceiptCheckName,
    ReceiptCheckResult,
    ReceiptReadStatus,
    ReceiptVerdict,
)

# Common Indian city spellings, so "Bangalore" on a receipt matches a trip to "Bengaluru".
CITY_ALIASES = {
    "bangalore": "bengaluru",
    "bombay": "mumbai",
    "madras": "chennai",
    "calcutta": "kolkata",
    "gurgaon": "gurugram",
    "cochin": "kochi",
    "poona": "pune",
    "trivandrum": "thiruvananthapuram",
    "mysore": "mysuru",
    "baroda": "vadodara",
    "benares": "varanasi",
    "new delhi": "delhi",
}


@dataclass(frozen=True)
class RuleConfig:
    amount_tolerance_pct: Decimal = Decimal("1.0")
    amount_tolerance_min: Decimal = Decimal("10")
    date_tolerance_days: int = 1
    ai_generated_threshold: float = 0.5

    @classmethod
    def from_settings(cls, settings) -> "RuleConfig":
        return cls(
            amount_tolerance_pct=Decimal(str(settings.receipt_amount_tolerance_pct)),
            amount_tolerance_min=Decimal(str(settings.receipt_amount_tolerance_min_inr)),
            date_tolerance_days=settings.receipt_date_tolerance_days,
            ai_generated_threshold=settings.receipt_ai_generated_threshold,
        )


@dataclass(frozen=True)
class Reading:
    """What was read from the photo (a receipt_checks row)."""
    status: ReceiptReadStatus
    is_receipt: bool | None = None
    total_amount: Decimal | None = None
    receipt_date: date | None = None
    city: str | None = None
    from_place: str | None = None
    to_place: str | None = None
    ai_generated_score: float | None = None


@dataclass(frozen=True)
class LineFacts:
    """The expense line as typed (any value may still be missing while the form is being filled)."""
    expense_type: ExpenseCategory | None
    amount: Decimal | None
    expense_date: date | None


@dataclass(frozen=True)
class TripFacts:
    destination: str
    created_on: date


@dataclass(frozen=True)
class Verification:
    verdict: ReceiptVerdict
    checks: list[ReceiptCheckItem]


def _inr(amount: Decimal) -> str:
    return f"Rs {amount:,.2f}"


def normalise_place(value: str | None) -> str:
    """'Bengaluru, Karnataka' -> 'bengaluru'; 'BANGALORE ' -> 'bengaluru' (accents and punctuation removed)."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z ,]", " ", text)
    first = re.sub(r"\s+", " ", text.split(",")[0]).strip()
    return CITY_ALIASES.get(first, first)


def places_match(on_receipt: str | None, destination: str) -> bool:
    """True when the receipt place and the destination name the same city (either may be longer)."""
    a, b = normalise_place(on_receipt), normalise_place(destination)
    if not a or not b:
        return False
    return a == b or a in b or b in a or any(CITY_ALIASES.get(w, w) == b for w in a.split())


def _check(name: ReceiptCheckName, result: ReceiptCheckResult, message: str) -> ReceiptCheckItem:
    return ReceiptCheckItem(check=name, result=result, message=message)


def check_amount(reading: Reading, line: LineFacts, cfg: RuleConfig) -> ReceiptCheckItem:
    if line.amount is None:
        return _check(ReceiptCheckName.AMOUNT, ReceiptCheckResult.MISSING_INPUT, "Enter the amount to check it")
    if reading.total_amount is None:
        return _check(ReceiptCheckName.AMOUNT, ReceiptCheckResult.FAIL, "No total amount could be found on the receipt")
    tolerance = max(line.amount * cfg.amount_tolerance_pct / Decimal(100), cfg.amount_tolerance_min)
    if abs(reading.total_amount - line.amount) <= tolerance:
        return _check(ReceiptCheckName.AMOUNT, ReceiptCheckResult.PASS, f"Receipt total {_inr(reading.total_amount)} matches")
    return _check(
        ReceiptCheckName.AMOUNT,
        ReceiptCheckResult.FAIL,
        f"Receipt total is {_inr(reading.total_amount)}, but {_inr(line.amount)} was entered",
    )


def check_date(reading: Reading, line: LineFacts, trip: TripFacts, cfg: RuleConfig) -> ReceiptCheckItem:
    if line.expense_date is None:
        return _check(ReceiptCheckName.DATE, ReceiptCheckResult.MISSING_INPUT, "Enter the expense date to check it")
    if reading.receipt_date is None:
        return _check(ReceiptCheckName.DATE, ReceiptCheckResult.FAIL, "No date could be found on the receipt")
    on_receipt = reading.receipt_date.strftime("%d %b %Y")
    if reading.receipt_date < trip.created_on:
        return _check(
            ReceiptCheckName.DATE,
            ReceiptCheckResult.FAIL,
            f"Receipt is dated {on_receipt}, before the trip was created ({trip.created_on.strftime('%d %b %Y')})",
        )
    if abs((reading.receipt_date - line.expense_date).days) > cfg.date_tolerance_days:
        return _check(
            ReceiptCheckName.DATE,
            ReceiptCheckResult.FAIL,
            f"Receipt is dated {on_receipt}, but {line.expense_date.strftime('%d %b %Y')} was entered",
        )
    return _check(ReceiptCheckName.DATE, ReceiptCheckResult.PASS, f"Receipt date {on_receipt} matches")


def check_place(reading: Reading, line: LineFacts, trip: TripFacts) -> ReceiptCheckItem:
    """Airfare: the route must include the destination. Everything else: the city must be the destination."""
    destination = trip.destination.split(",")[0].strip()
    if line.expense_type == ExpenseCategory.AIRFARE:
        route = [p for p in (reading.from_place, reading.to_place) if p]
        if not route:
            if reading.city and places_match(reading.city, trip.destination):
                return _check(ReceiptCheckName.PLACE, ReceiptCheckResult.PASS, f"Receipt mentions {destination}")
            return _check(ReceiptCheckName.PLACE, ReceiptCheckResult.NOT_ON_RECEIPT, "No route printed on the receipt")
        if any(places_match(p, trip.destination) for p in route):
            return _check(ReceiptCheckName.PLACE, ReceiptCheckResult.PASS, f"Route {' to '.join(route)} includes {destination}")
        return _check(
            ReceiptCheckName.PLACE,
            ReceiptCheckResult.FAIL,
            f"Route {' to '.join(route)} does not include the trip destination {destination}",
        )
    if not reading.city:
        return _check(ReceiptCheckName.PLACE, ReceiptCheckResult.NOT_ON_RECEIPT, "No city printed on the receipt")
    if places_match(reading.city, trip.destination):
        return _check(ReceiptCheckName.PLACE, ReceiptCheckResult.PASS, f"Receipt is from {destination}")
    return _check(
        ReceiptCheckName.PLACE,
        ReceiptCheckResult.FAIL,
        f"Receipt is from {reading.city}, not the trip destination {destination}",
    )


def check_authenticity(reading: Reading, cfg: RuleConfig) -> ReceiptCheckItem:
    score = reading.ai_generated_score
    if score is None:
        return _check(ReceiptCheckName.AUTHENTICITY, ReceiptCheckResult.NOT_CHECKED, "Image authenticity was not checked")
    if score >= cfg.ai_generated_threshold:
        return _check(
            ReceiptCheckName.AUTHENTICITY,
            ReceiptCheckResult.FAIL,
            f"The image looks AI-generated or edited ({round(score * 100)}% likely)",
        )
    return _check(ReceiptCheckName.AUTHENTICITY, ReceiptCheckResult.PASS, "No signs of an AI-generated image")


def verify(reading: Reading | None, line: LineFacts, trip: TripFacts, cfg: RuleConfig) -> Verification:
    """Compare one reading with one line. The same inputs always give the same result."""
    if reading is None or reading.status == ReceiptReadStatus.ERROR:
        return Verification(ReceiptVerdict.NOT_VERIFIED, [])
    if reading.status == ReceiptReadStatus.UNREADABLE or reading.is_receipt is False:
        return Verification(ReceiptVerdict.UNREADABLE, [])
    checks = [
        check_amount(reading, line, cfg),
        check_date(reading, line, trip, cfg),
        check_place(reading, line, trip),
        check_authenticity(reading, cfg),
    ]
    results = {c.result for c in checks}
    if ReceiptCheckResult.FAIL in results:
        return Verification(ReceiptVerdict.INVALID, checks)
    if ReceiptCheckResult.MISSING_INPUT in results:
        return Verification(ReceiptVerdict.INCOMPLETE, checks)
    return Verification(ReceiptVerdict.VALID, checks)


def failure_summary(checks: list[ReceiptCheckItem]) -> str:
    """Comment for the SYSTEM rejection: every failed check, in order (always >= 10 characters)."""
    failed = [c.message for c in checks if c.result == ReceiptCheckResult.FAIL]
    return "Automated receipt check failed: " + ("; ".join(failed) if failed else "receipt did not match") + "."

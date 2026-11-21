"""
Trip dates (past start, end = start, end < start, > 30 days, > 365 days), destination, amount, category,
future expense date, missing evidence_id, same photo twice, decision comment rules, login email.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0 > Testing strategy
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import (
    ExpenseLineCreate,
    LoginRequest,
    TicketCreate,
    TicketDecisionRequest,
    TripCreate,
    TripDecisionRequest,
    today,
)


def trip(start: int, end: int, destination: str = "Bengaluru") -> dict:
    return {"destination": destination, "start_date": today() + timedelta(days=start),
            "end_date": today() + timedelta(days=end), "purpose": "Client workshop for annual planning"}


def line(**overrides) -> dict:
    return {"expense_type": "MEALS", "amount": "800", "expense_date": today(), "description": "Lunch",
            "evidence_id": uuid4(), **overrides}


# ---------------------------------------------------------------- trip dates [POL-3.2]
@pytest.mark.parametrize(
    "start,end",
    [(0, 1), (0, 29), (365, 366)],          # today is allowed; 30 days inclusive; start exactly +365
)
def test_valid_trip_dates(start: int, end: int) -> None:
    TripCreate(**trip(start, end))


@pytest.mark.parametrize(
    "start,end,reason",
    [(-1, 1, "past start"), (5, 5, "end = start"), (5, 4, "end < start"), (0, 30, "31 days"), (366, 367, "> 365 days")],
)
def test_invalid_trip_dates(start: int, end: int, reason: str) -> None:
    with pytest.raises(ValidationError):
        TripCreate(**trip(start, end))


@pytest.mark.parametrize("destination", ["B", "Hyd3rabad", "<script>", "Pune!"])
def test_invalid_destination(destination: str) -> None:
    with pytest.raises(ValidationError):
        TripCreate(**trip(3, 5, destination))


def test_destination_spaces_are_cleaned() -> None:
    assert TripCreate(**trip(3, 5, "  St.  John's  ")).destination == "St. John's"


# ---------------------------------------------------------------- expense lines [POL-6.x, 7.x, 8.1]
@pytest.mark.parametrize("amount", ["0", "-5", "200000.01", "10.123"])
def test_invalid_amounts(amount: str) -> None:
    with pytest.raises(ValidationError):
        ExpenseLineCreate(**line(amount=amount))


def test_hard_cap_amount_is_allowed() -> None:
    ExpenseLineCreate(**line(amount="200000.00"))


def test_unknown_category_is_refused() -> None:
    with pytest.raises(ValidationError):
        ExpenseLineCreate(**line(expense_type="ENTERTAINMENT"))


def test_future_expense_date_is_refused() -> None:
    with pytest.raises(ValidationError):
        ExpenseLineCreate(**line(expense_date=today() + timedelta(days=1)))


def test_missing_evidence_id_is_refused() -> None:
    body = line()
    del body["evidence_id"]
    with pytest.raises(ValidationError):
        ExpenseLineCreate(**body)


def test_invoice_number_is_optional_and_normalised() -> None:
    assert ExpenseLineCreate(**line(invoice_number="  ")).invoice_number is None
    assert ExpenseLineCreate(**line(invoice_number="inv-88231")).invoice_number == "INV-88231"
    with pytest.raises(ValidationError):
        ExpenseLineCreate(**line(invoice_number="a b"))


def test_same_photo_or_invoice_twice_in_one_ticket() -> None:
    photo = uuid4()
    with pytest.raises(ValidationError):
        TicketCreate(expenses=[line(evidence_id=photo), line(evidence_id=photo)])
    with pytest.raises(ValidationError):
        TicketCreate(expenses=[line(invoice_number="INV-1"), line(invoice_number="inv-1")])


def test_ticket_needs_1_to_20_lines() -> None:
    with pytest.raises(ValidationError):
        TicketCreate(expenses=[])
    with pytest.raises(ValidationError):
        TicketCreate(expenses=[line() for _ in range(21)])
    TicketCreate(expenses=[line() for _ in range(20)])


# ---------------------------------------------------------------- decisions [POL-3.6, 9.4]
def test_trip_decision_comment_rules() -> None:
    TripDecisionRequest(decision="APPROVED")
    TripDecisionRequest(decision="REJECTED", review_comment="Budget is frozen this quarter.")
    with pytest.raises(ValidationError):
        TripDecisionRequest(decision="REJECTED", review_comment="   short   ")


def test_ticket_decision_reason_and_comment_rules() -> None:
    TicketDecisionRequest(decision="APPROVED")
    TicketDecisionRequest(decision="REJECTED", rejection_reason="OTHER", review_comment="Not a business expense.")
    with pytest.raises(ValidationError):
        TicketDecisionRequest(decision="REJECTED", review_comment="Not a business expense.")
    with pytest.raises(ValidationError):
        TicketDecisionRequest(decision="REJECTED", rejection_reason="OTHER")
    with pytest.raises(ValidationError):
        TicketDecisionRequest(decision="APPROVED", rejection_reason="OTHER")


# ---------------------------------------------------------------- login email
def test_login_email_is_checked_and_lower_cased() -> None:
    assert LoginRequest(email="Rohan.Mehta@Veridian.Example", password="Password1").email == "rohan.mehta@veridian.example"
    with pytest.raises(ValidationError):
        LoginRequest(email="not-an-email", password="Password1")


def test_login_password_only_needs_one_character() -> None:
    """Team decision: min_length 1 (a short wrong password gets the normal 401, not a 422)."""
    assert LoginRequest(email="a@b.example", password="x").password == "x"
    with pytest.raises(ValidationError):
        LoginRequest(email="a@b.example", password="")

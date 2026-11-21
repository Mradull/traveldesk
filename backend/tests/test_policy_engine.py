"""
Thresholds below/equal/above per category; duplicate by photo hash and invoice; rejected tickets ignored; routing.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0 > Testing strategy
"""

from decimal import Decimal

import pytest

from app.core.config import get_settings
from app.schemas import ExpenseCategory, PolicyRuleCode, TicketRouting, TicketStatus, today
from app.services.policy_engine import PolicyConfig, PolicyLine, evaluate_line, route

THRESHOLDS = {"AIRFARE": 20000, "LODGING": 7500, "MEALS": 1500, "GROUND_TRANSPORT": 3000, "INCIDENTALS": 1000}


def config() -> PolicyConfig:
    return PolicyConfig.from_settings(get_settings())


def codes(amount: Decimal, category: str, sha: str = "a" * 64, invoice: str | None = None,
          hashes: set[str] | None = None, invoices: set[str] | None = None) -> list[PolicyRuleCode]:
    flags = evaluate_line(
        PolicyLine(ExpenseCategory(category), amount, sha, invoice), config(), hashes or set(), invoices or set()
    )
    return [flag.rule_code for flag in flags]


@pytest.mark.parametrize("category,threshold", THRESHOLDS.items())
def test_threshold_below_equal_above(category: str, threshold: int) -> None:
    """[POL-6.2]: above the threshold is flagged; equal is fine."""
    limit = Decimal(threshold)
    assert codes(limit - Decimal("0.01"), category) == []
    assert codes(limit, category) == []
    assert codes(limit + Decimal("0.01"), category) == [PolicyRuleCode.OVER_THRESHOLD]


def test_over_threshold_flag_details() -> None:
    flags = evaluate_line(PolicyLine(ExpenseCategory.MEALS, Decimal("1800"), "a" * 64, None), config(), set(), set())
    assert flags[0].message == "MEALS amount 1,800.00 is above the 1,500.00 review threshold"
    assert (flags[0].policy_ref, flags[0].threshold_amount) == ("[POL-6.2]", Decimal("1500"))


def test_duplicate_by_photo_hash_and_by_invoice() -> None:
    """[POL-7.4]: same photo fingerprint, or same invoice number (case-insensitive)."""
    assert codes(Decimal("100"), "MEALS", sha="b" * 64, hashes={"b" * 64}) == [PolicyRuleCode.DUPLICATE_RECEIPT]
    assert codes(Decimal("100"), "MEALS", invoice="inv-77", invoices={"INV-77"}) == [PolicyRuleCode.DUPLICATE_RECEIPT]
    assert codes(Decimal("100"), "MEALS", sha="c" * 64, invoice="INV-1", hashes={"b" * 64}, invoices={"INV-2"}) == []


def test_both_flags_on_one_line() -> None:
    assert codes(Decimal("9000"), "LODGING", sha="d" * 64, hashes={"d" * 64}) == [
        PolicyRuleCode.OVER_THRESHOLD, PolicyRuleCode.DUPLICATE_RECEIPT
    ]


def test_routing_zero_flags_vs_flags() -> None:
    """[POL-9.2]: zero flags -> AUTO_APPROVED / AUTO; any flag -> PENDING / MANAGER."""
    assert route(0) == (TicketStatus.AUTO_APPROVED, TicketRouting.AUTO)
    assert route(1) == (TicketStatus.PENDING, TicketRouting.MANAGER)
    assert route(3) == (TicketStatus.PENDING, TicketRouting.MANAGER)


def _line(evidence_id: str, invoice: str | None = None) -> dict:
    body = {"expense_type": "MEALS", "amount": "500", "expense_date": today().isoformat(),
            "description": "Client lunch", "evidence_id": evidence_id}
    if invoice:
        body["invoice_number"] = invoice
    return body


def test_duplicates_are_found_across_tickets_but_rejected_tickets_are_ignored(
    api_client, team, make_trip, make_evidence, auth_header
) -> None:
    """Same photo bytes uploaded again: flagged while the first ticket stands; not flagged once the
    first ticket is REJECTED (so a rejected photo can be re-uploaded for its replacement)."""
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"])
    url = f"/api/v1/trips/{trip_id}/tickets"
    photo_bytes = b"\xff\xd8\xff\xe0same-receipt"

    first = api_client.post(url, headers=auth_header(rohan), json={"expenses": [
        _line(make_evidence(rohan["employee_id"], photo_bytes)), _line(make_evidence(rohan["employee_id"]), "INV-55")
    ]}).json()
    assert first["status"] == "AUTO_APPROVED"

    dup_photo = api_client.post(url, headers=auth_header(rohan), json={"expenses": [
        _line(make_evidence(rohan["employee_id"], photo_bytes))
    ]}).json()
    assert dup_photo["status"] == "PENDING"
    assert dup_photo["expenses"][0]["flags"][0]["rule_code"] == "DUPLICATE_RECEIPT"

    dup_invoice = api_client.post(url, headers=auth_header(rohan), json={"expenses": [
        _line(make_evidence(rohan["employee_id"]), "inv-55")
    ]}).json()
    assert dup_invoice["expenses"][0]["flags"][0]["rule_code"] == "DUPLICATE_RECEIPT"

    # A photo + invoice that only appear on a REJECTED ticket do not count as already claimed.
    other_bytes = b"\xff\xd8\xff\xe0rejected-receipt"
    flagged = api_client.post(url, headers=auth_header(rohan), json={"expenses": [
        _line(make_evidence(rohan["employee_id"], other_bytes), "INV-99"), _line(make_evidence(rohan["employee_id"], other_bytes))
    ]}).json()
    assert flagged["status"] == "PENDING"                    # 2nd line repeats the 1st line's photo
    api_client.post(f"/api/v1/tickets/{flagged['ticket_id']}/decision", headers=auth_header(team["manager"]),
                    json={"decision": "REJECTED", "rejection_reason": "INCORRECT_EVIDENCE",
                          "review_comment": "Same photo attached twice."})

    again = api_client.post(url, headers=auth_header(rohan), json={"expenses": [
        _line(make_evidence(rohan["employee_id"], other_bytes), "INV-99")
    ]}).json()
    assert again["status"] == "AUTO_APPROVED" and again["expenses"][0]["flags"] == []

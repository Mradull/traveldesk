"""Receipt verification rules (pure functions, no database, no AI). Owner: Mradul (M3)."""
from datetime import date
from decimal import Decimal

from app.schemas import ExpenseCategory, ReceiptCheckName, ReceiptCheckResult, ReceiptReadStatus, ReceiptVerdict
from app.services import receipt_rules as rr

CFG = rr.RuleConfig()
TRIP = rr.TripFacts(destination="Bengaluru", created_on=date(2026, 11, 20))


def reading(**kw):
    base = dict(status=ReceiptReadStatus.READ, is_receipt=True, total_amount=Decimal("1850.00"),
                receipt_date=date(2026, 11, 24), city="Bengaluru", ai_generated_score=0.02)
    base.update(kw)
    return rr.Reading(**base)


def line(**kw):
    base = dict(expense_type=ExpenseCategory.MEALS, amount=Decimal("1850.00"), expense_date=date(2026, 11, 24))
    base.update(kw)
    return rr.LineFacts(**base)


def result_of(checks, name):
    return next(c.result for c in checks if c.check == name)


def test_matching_receipt_is_valid():
    v = rr.verify(reading(), line(), TRIP, CFG)
    assert v.verdict == ReceiptVerdict.VALID
    assert {c.result for c in v.checks} == {ReceiptCheckResult.PASS}


def test_amount_within_tolerance_passes_and_outside_fails():
    # tolerance = max(1% of 1850 = 18.50, 10) = 18.50
    assert rr.verify(reading(total_amount=Decimal("1868.50")), line(), TRIP, CFG).verdict == ReceiptVerdict.VALID
    v = rr.verify(reading(total_amount=Decimal("2400.00")), line(), TRIP, CFG)
    assert v.verdict == ReceiptVerdict.INVALID
    assert result_of(v.checks, ReceiptCheckName.AMOUNT) == ReceiptCheckResult.FAIL


def test_small_amounts_use_the_rupee_minimum():
    # 1% of 400 is 4, so the Rs 10 minimum applies
    small = line(amount=Decimal("400.00"))
    assert rr.verify(reading(total_amount=Decimal("409.00")), small, TRIP, CFG).verdict == ReceiptVerdict.VALID
    assert rr.verify(reading(total_amount=Decimal("411.00")), small, TRIP, CFG).verdict == ReceiptVerdict.INVALID


def test_missing_total_or_date_on_receipt_fails():
    assert rr.verify(reading(total_amount=None), line(), TRIP, CFG).verdict == ReceiptVerdict.INVALID
    assert rr.verify(reading(receipt_date=None), line(), TRIP, CFG).verdict == ReceiptVerdict.INVALID


def test_date_tolerance_one_day():
    assert rr.verify(reading(receipt_date=date(2026, 11, 25)), line(), TRIP, CFG).verdict == ReceiptVerdict.VALID
    v = rr.verify(reading(receipt_date=date(2026, 11, 27)), line(), TRIP, CFG)
    assert result_of(v.checks, ReceiptCheckName.DATE) == ReceiptCheckResult.FAIL


def test_receipt_before_trip_created_fails():
    v = rr.verify(reading(receipt_date=date(2026, 11, 19)), line(expense_date=date(2026, 11, 20)), TRIP, CFG)
    assert result_of(v.checks, ReceiptCheckName.DATE) == ReceiptCheckResult.FAIL
    assert "before the trip was created" in next(c.message for c in v.checks if c.check == ReceiptCheckName.DATE)


def test_city_aliases_and_address_text_match():
    assert rr.places_match("BANGALORE", "Bengaluru")
    assert rr.places_match("Bengaluru, Karnataka 560001", "Bengaluru")
    assert rr.places_match("Mumbai", "Bombay")
    assert not rr.places_match("Chennai", "Bengaluru")


def test_wrong_city_fails_but_no_city_is_not_a_failure():
    wrong = rr.verify(reading(city="Chennai"), line(), TRIP, CFG)
    assert result_of(wrong.checks, ReceiptCheckName.PLACE) == ReceiptCheckResult.FAIL
    none = rr.verify(reading(city=None), line(), TRIP, CFG)
    assert result_of(none.checks, ReceiptCheckName.PLACE) == ReceiptCheckResult.NOT_ON_RECEIPT
    assert none.verdict == ReceiptVerdict.VALID


def test_airfare_route_must_include_destination():
    air = line(expense_type=ExpenseCategory.AIRFARE)
    ok = rr.verify(reading(city=None, from_place="Mumbai", to_place="Bangalore"), air, TRIP, CFG)
    assert result_of(ok.checks, ReceiptCheckName.PLACE) == ReceiptCheckResult.PASS
    back = rr.verify(reading(city=None, from_place="Bengaluru", to_place="Mumbai"), air, TRIP, CFG)
    assert result_of(back.checks, ReceiptCheckName.PLACE) == ReceiptCheckResult.PASS     # return flight
    wrong = rr.verify(reading(city=None, from_place="Delhi", to_place="Goa"), air, TRIP, CFG)
    assert wrong.verdict == ReceiptVerdict.INVALID


def test_ai_generated_image_fails_and_unchecked_is_not_a_failure():
    fake = rr.verify(reading(ai_generated_score=0.91), line(), TRIP, CFG)
    assert fake.verdict == ReceiptVerdict.INVALID
    assert "AI-generated" in next(c.message for c in fake.checks if c.check == ReceiptCheckName.AUTHENTICITY)
    unchecked = rr.verify(reading(ai_generated_score=None), line(), TRIP, CFG)
    assert result_of(unchecked.checks, ReceiptCheckName.AUTHENTICITY) == ReceiptCheckResult.NOT_CHECKED
    assert unchecked.verdict == ReceiptVerdict.VALID


def test_unreadable_error_and_incomplete():
    assert rr.verify(reading(status=ReceiptReadStatus.UNREADABLE), line(), TRIP, CFG).verdict == ReceiptVerdict.UNREADABLE
    assert rr.verify(reading(is_receipt=False), line(), TRIP, CFG).verdict == ReceiptVerdict.UNREADABLE
    assert rr.verify(reading(status=ReceiptReadStatus.ERROR), line(), TRIP, CFG).verdict == ReceiptVerdict.NOT_VERIFIED
    assert rr.verify(None, line(), TRIP, CFG).verdict == ReceiptVerdict.NOT_VERIFIED
    assert rr.verify(reading(), line(amount=None), TRIP, CFG).verdict == ReceiptVerdict.INCOMPLETE


def test_failure_summary_lists_every_failed_check():
    v = rr.verify(reading(total_amount=Decimal("2400"), city="Chennai"), line(), TRIP, CFG)
    text = rr.failure_summary(v.checks)
    assert "2,400.00" in text and "Chennai" in text and len(text) >= 10

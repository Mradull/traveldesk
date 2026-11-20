"""
Trip state machine: create/edit (v2.0 date rules), list/detail with can_* flags, earliest_expense_date (= created_on),
auto_complete_on (= start + 90 days), manager completion on/after end date.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from datetime import timedelta

from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.repositories import trip_repo
from app.schemas import (
    CurrentUser,
    TripCreate,
    TripOut,
)


def create_trip(
    db: Connection,
    employee: CurrentUser,
    request: TripCreate,
) -> TripOut:
    """Create an In Progress trip owned by the authenticated employee."""
    row = trip_repo.create(db, employee.employee_id, request)
    trip = TripOut(
        **row,
        status_label="In Progress",
        earliest_expense_date=row["created_on"],
        auto_complete_on=row["start_date"]
        + timedelta(days=get_settings().policy_trip_auto_complete_days_after_start),
        can_edit=True,
        can_raise_ticket=False,
        can_decide=False,
        can_complete=False,
    )
    db.commit()
    return trip

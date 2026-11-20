"""
Runs the three SQL demonstrations for the manager's direct reports.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0  (Required SQL demonstrations; US-17; EY brief section 03)
"""

from sqlalchemy.engine import Connection

from app.repositories import report_repo
from app.schemas import CurrentUser, PendingExpenseOut, SpendByTripCategoryRow, TripExpenseJoinRow


def trip_expenses(db: Connection, manager: CurrentUser) -> list[TripExpenseJoinRow]:
    """Demo 1: employee, trip, destination, expense type and amount."""
    return [TripExpenseJoinRow(**row) for row in report_repo.trip_expenses(db, manager.employee_id)]


def spend_by_trip_category(db: Connection, manager: CurrentUser) -> list[SpendByTripCategoryRow]:
    """Demo 2: approved spending by trip and category, with trip total rows (expense_type null)."""
    return [SpendByTripCategoryRow(**row) for row in report_repo.spend_by_trip_category(db, manager.employee_id)]


def pending_expenses(db: Connection, manager: CurrentUser) -> list[PendingExpenseOut]:
    """Demo 3: flagged lines in pending tickets (GET /expenses/pending)."""
    return [PendingExpenseOut(**row) for row in report_repo.pending_flagged_expenses(db, manager.employee_id)]

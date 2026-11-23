"""
Runs the three SQL demonstrations for the manager's direct reports, and the employee dashboard.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0  (Required SQL demonstrations; US-17; EY brief section 03)
"""

from sqlalchemy.engine import Connection

from app.repositories import report_repo
from app.schemas import (
    CategorySpendRow,
    CurrentUser,
    EmployeeDashboardOut,
    PendingExpenseOut,
    SpendByTripCategoryRow,
    TripExpenseJoinRow,
    TripListItemOut,
)
from app.services import trip_service

RECENT_TRIPS_ON_DASHBOARD = 5


def trip_expenses(db: Connection, manager: CurrentUser) -> list[TripExpenseJoinRow]:
    """Demo 1: employee, trip, destination, expense type and amount."""
    return [TripExpenseJoinRow(**row) for row in report_repo.trip_expenses(db, manager.employee_id)]


def spend_by_trip_category(db: Connection, manager: CurrentUser) -> list[SpendByTripCategoryRow]:
    """Demo 2: approved spending by trip and category, with trip total rows (expense_type null)."""
    return [SpendByTripCategoryRow(**row) for row in report_repo.spend_by_trip_category(db, manager.employee_id)]


def pending_expenses(db: Connection, manager: CurrentUser) -> list[PendingExpenseOut]:
    """Demo 3: flagged lines in pending tickets (GET /expenses/pending)."""
    return [PendingExpenseOut(**row) for row in report_repo.pending_flagged_expenses(db, manager.employee_id)]


def employee_dashboard(db: Connection, employee: CurrentUser) -> EmployeeDashboardOut:
    """GET /dashboard/employee: the caller's own counts, claimed money, newest trips and spend by category."""
    recent = report_repo.employee_recent_trips(db, employee.employee_id, RECENT_TRIPS_ON_DASHBOARD)
    return EmployeeDashboardOut(
        **report_repo.employee_dashboard_totals(db, employee.employee_id),
        recent_trips=[
            TripListItemOut(
                **row,
                status_label=trip_service.status_label(row["approval_status"], row["trip_state"]),
                auto_complete_on=trip_service.auto_complete_on(row["start_date"]),
            )
            for row in recent
        ],
        spend_by_category=[
            CategorySpendRow(**row) for row in report_repo.employee_spend_by_category(db, employee.employee_id)
        ],
    )

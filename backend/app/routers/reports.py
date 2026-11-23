"""
Manager only: GET /reports/trip-expenses, GET /reports/spend-by-trip-category (the required SQL demonstrations).
Employee only: GET /dashboard/employee (team addition to Spec v2.0, for M3's DashboardPage).

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Connection

from app.core.deps import get_db, require_employee, require_manager
from app.schemas import CurrentUser, EmployeeDashboardOut, SpendByTripCategoryRow, TripExpenseJoinRow
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])
dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])

Db = Annotated[Connection, Depends(get_db)]
Manager = Annotated[CurrentUser, Depends(require_manager)]
Employee = Annotated[CurrentUser, Depends(require_employee)]


@router.get("/trip-expenses", response_model=list[TripExpenseJoinRow])
def trip_expenses(manager: Manager, db: Db) -> list[TripExpenseJoinRow]:
    """SQL demo 1: trips joined with expenses for my direct reports."""
    return report_service.trip_expenses(db, manager)


@router.get("/spend-by-trip-category", response_model=list[SpendByTripCategoryRow])
def spend_by_trip_category(manager: Manager, db: Db) -> list[SpendByTripCategoryRow]:
    """SQL demo 2: approved spending by trip and category, with trip totals."""
    return report_service.spend_by_trip_category(db, manager)


@dashboard_router.get("/employee", response_model=EmployeeDashboardOut)
def employee_dashboard(employee: Employee, db: Db) -> EmployeeDashboardOut:
    """My own dashboard numbers (employee): trip counts, claimed money, newest trips, spend by category."""
    return report_service.employee_dashboard(db, employee)

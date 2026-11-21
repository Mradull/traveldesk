"""
GET /trips/{trip_id}/expenses, GET /expenses/pending, GET /expenses/{id}, GET /expenses/{id}/policy-check.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Connection

from app.core.deps import get_current_user, get_db, require_manager
from app.schemas import CurrentUser, ExpenseOut, PendingExpenseOut, PolicyCheckOut
from app.services import report_service, ticket_service

router = APIRouter(tags=["expenses"])

Db = Annotated[Connection, Depends(get_db)]
AnyUser = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("/trips/{trip_id}/expenses", response_model=list[ExpenseOut])
def list_trip_expenses(trip_id: int, user: AnyUser, db: Db) -> list[ExpenseOut]:
    """Expense lines of one trip (owner or approving manager)."""
    return ticket_service.list_trip_expenses(db, user, trip_id)


# Fixed path before /expenses/{expense_id} (spec > Route order).
@router.get("/expenses/pending", response_model=list[PendingExpenseOut])
def list_pending_expenses(
    manager: Annotated[CurrentUser, Depends(require_manager)], db: Db
) -> list[PendingExpenseOut]:
    """SQL demo 3: flagged lines in pending tickets of my direct reports (manager)."""
    return report_service.pending_expenses(db, manager)


@router.get("/expenses/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: int, user: AnyUser, db: Db) -> ExpenseOut:
    """One expense line (owner or approving manager)."""
    return ticket_service.get_expense(db, user, expense_id)


@router.get("/expenses/{expense_id}/policy-check", response_model=PolicyCheckOut)
def policy_check(expense_id: int, user: AnyUser, db: Db) -> PolicyCheckOut:
    """US-18: re-run the policy rules for one line (read-only, no data change)."""
    return ticket_service.policy_check(db, user, expense_id)

# No PUT/PATCH/DELETE on /expenses/{id}: FastAPI answers 405 (US-15).

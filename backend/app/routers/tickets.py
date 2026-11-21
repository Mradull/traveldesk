"""
POST/GET /trips/{trip_id}/tickets, GET /tickets, GET /tickets/pending, GET /tickets/{id}, POST /tickets/{id}/decision.
No PUT/PATCH/DELETE (405).

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.engine import Connection

from app.core.deps import get_current_user, get_db, require_employee, require_manager
from app.schemas import (
    CurrentUser,
    PendingTicketOut,
    TicketCreate,
    TicketDecisionRequest,
    TicketDetailOut,
    TicketStatus,
    TicketSummaryOut,
)
from app.services import approval_service, ticket_service

router = APIRouter(tags=["tickets"])

Db = Annotated[Connection, Depends(get_db)]
AnyUser = Annotated[CurrentUser, Depends(get_current_user)]
Employee = Annotated[CurrentUser, Depends(require_employee)]
Manager = Annotated[CurrentUser, Depends(require_manager)]


@router.post("/trips/{trip_id}/tickets", response_model=TicketDetailOut, status_code=status.HTTP_201_CREATED)
def create_ticket(trip_id: int, request: TicketCreate, employee: Employee, db: Db) -> TicketDetailOut:
    """US-11/US-16: raise a ticket (or a replacement for a rejected one) on my Active trip."""
    return ticket_service.create_ticket(db, employee, trip_id, request)


@router.get("/trips/{trip_id}/tickets", response_model=list[TicketSummaryOut])
def list_trip_tickets(trip_id: int, user: AnyUser, db: Db) -> list[TicketSummaryOut]:
    """Tickets of one trip (owner or approving manager)."""
    return ticket_service.list_trip_tickets(db, user, trip_id)


@router.get("/tickets", response_model=list[TicketSummaryOut])
def list_my_tickets(
    employee: Employee,
    db: Db,
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    trip_id: Annotated[int | None, Query()] = None,
) -> list[TicketSummaryOut]:
    """US-13: all my tickets across trips; optional ?status= and ?trip_id= filters."""
    return ticket_service.list_my_tickets(db, employee, status_filter, trip_id)


# Fixed path before /tickets/{ticket_id} (spec > Route order).
@router.get("/tickets/pending", response_model=list[PendingTicketOut])
def list_pending_tickets(manager: Manager, db: Db) -> list[PendingTicketOut]:
    """US-14: PENDING tickets of my direct reports, with flag codes."""
    return ticket_service.list_pending_tickets(db, manager)


@router.get("/tickets/{ticket_id}", response_model=TicketDetailOut)
def get_ticket(ticket_id: int, user: AnyUser, db: Db) -> TicketDetailOut:
    """Ticket detail for the owner or the approving manager (others 404)."""
    return ticket_service.get_ticket(db, user, ticket_id)


@router.post("/tickets/{ticket_id}/decision", response_model=TicketDetailOut)
def decide_ticket(ticket_id: int, request: TicketDecisionRequest, manager: Manager, db: Db) -> TicketDetailOut:
    """US-14: approve (comment optional) or reject (rejection_reason + 10-character comment)."""
    return approval_service.decide_ticket(db, manager, ticket_id, request)

# No PUT/PATCH/DELETE routes exist for tickets or decisions: FastAPI answers 405, which the
# error handler turns into the METHOD_NOT_ALLOWED envelope (US-15).

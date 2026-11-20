"""
POST/GET /trips, GET/PUT /trips/{id}, GET /trips/pending, GET /trips/to-complete,
POST /trips/{id}/decision, POST /trips/{id}/complete. Declare /pending and /to-complete before /{trip_id}.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.engine import Connection

from app.core.deps import get_current_user, get_db, require_employee, require_manager
from app.schemas import (
    CurrentUser,
    TripCreate,
    TripDecisionRequest,
    TripDetailOut,
    TripListItemOut,
    TripOut,
    TripUpdate,
)
from app.services import approval_service, trip_service

router = APIRouter(prefix="/trips", tags=["trips"])

Db = Annotated[Connection, Depends(get_db)]
Employee = Annotated[CurrentUser, Depends(require_employee)]
Manager = Annotated[CurrentUser, Depends(require_manager)]


@router.post("", response_model=TripOut, status_code=status.HTTP_201_CREATED)
def create_trip(request: TripCreate, employee: Employee, db: Db) -> TripOut:
    """US-05: submit a travel request (employee)."""
    return trip_service.create_trip(db, employee, request)


@router.get("", response_model=list[TripListItemOut])
def list_my_trips(
    employee: Employee,
    db: Db,
    when: Annotated[Literal["upcoming", "past", "all"], Query()] = "all",
) -> list[TripListItemOut]:
    """US-06: my trips. upcoming = ends today or later; past = ended before today; all."""
    return trip_service.list_my_trips(db, employee, when)


# Fixed paths first, so 'pending' / 'to-complete' are never read as a trip id (spec > Route order).
@router.get("/pending", response_model=list[TripListItemOut])
def list_pending_trips(manager: Manager, db: Db) -> list[TripListItemOut]:
    """US-08: In Progress trips of my direct reports (manager)."""
    return trip_service.list_pending_trips(db, manager)


@router.get("/to-complete", response_model=list[TripListItemOut])
def list_trips_to_complete(manager: Manager, db: Db) -> list[TripListItemOut]:
    """US-09: Active trips of my direct reports whose end date has been reached (manager)."""
    return trip_service.list_trips_to_complete(db, manager)


@router.get("/{trip_id}", response_model=TripDetailOut)
def get_trip(trip_id: int, user: Annotated[CurrentUser, Depends(get_current_user)], db: Db) -> TripDetailOut:
    """Trip detail for the owner or the approving manager (others 404)."""
    return trip_service.get_trip_detail(db, user, trip_id)


@router.put("/{trip_id}", response_model=TripOut)
def update_trip(trip_id: int, request: TripUpdate, employee: Employee, db: Db) -> TripOut:
    """US-07: edit my trip while In Progress (409 TRIP_NOT_EDITABLE otherwise)."""
    return trip_service.update_trip(db, employee, trip_id, request)


@router.post("/{trip_id}/decision", response_model=TripOut)
def decide_trip(trip_id: int, request: TripDecisionRequest, manager: Manager, db: Db) -> TripOut:
    """US-08: approve or reject (review_comment of 10+ characters required to reject)."""
    return approval_service.decide_trip(db, manager, trip_id, request)


@router.post("/{trip_id}/complete", response_model=TripOut)
def complete_trip(trip_id: int, manager: Manager, db: Db) -> TripOut:
    """US-09: mark an Active trip completed on/after its end date (approving manager only)."""
    return trip_service.complete_trip(db, manager, trip_id)

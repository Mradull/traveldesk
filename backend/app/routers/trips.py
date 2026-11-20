"""
POST/GET /trips, GET/PUT /trips/{id}, GET /trips/pending, GET /trips/to-complete,
POST /trips/{id}/decision, POST /trips/{id}/complete. Declare /pending and /to-complete before /{trip_id}.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.engine import Connection

from app.core.deps import get_db, require_employee
from app.schemas import CurrentUser, TripCreate, TripOut
from app.services import trip_service

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post(
    "",
    response_model=TripOut,
    status_code=status.HTTP_201_CREATED,
)
def create_trip(
    request: TripCreate,
    employee: Annotated[CurrentUser, Depends(require_employee)],
    db: Annotated[Connection, Depends(get_db)],
) -> TripOut:
    return trip_service.create_trip(db, employee, request)

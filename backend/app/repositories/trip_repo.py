"""
SQL for travel_requests (incl. auto-complete UPDATE).

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.schemas import TripCreate


def create(
    db: Connection,
    employee_id: int,
    request: TripCreate,
) -> dict:
    """Insert a travel request and return the joined data needed for TripOut."""
    trip_id = db.execute(
        text(
            """
            INSERT INTO travel_requests
                (employee_id, destination, start_date, end_date, purpose)
            VALUES
                (:employee_id, :destination, :start_date, :end_date, :purpose)
            RETURNING trip_id
            """
        ),
        {
            "employee_id": employee_id,
            "destination": request.destination,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "purpose": request.purpose,
        },
    ).scalar_one()

    row = db.execute(
        text(
            """
            SELECT tr.trip_id, tr.trip_code, tr.employee_id,
                   e.full_name AS employee_name, e.department,
                   tr.destination, tr.start_date, tr.end_date, tr.purpose,
                   tr.approval_status, tr.trip_state, tr.created_on,
                   tr.completion_type, tr.completed_at, tr.created_at, tr.updated_at
            FROM travel_requests AS tr
            JOIN employees AS e ON e.employee_id = tr.employee_id
            WHERE tr.trip_id = :trip_id
            """
        ),
        {"trip_id": trip_id},
    ).mappings().one()
    return dict(row)

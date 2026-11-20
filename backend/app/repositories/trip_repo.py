"""
SQL for travel_requests (incl. auto-complete UPDATE).

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.schemas import TripCreate, TripUpdate

# One trip with its owner (name, department, line manager) and the completing manager's name.
# owner_manager_id lets the service decide whether the caller is the employee's approving manager.
_TRIP_SELECT = """
    SELECT tr.trip_id, tr.trip_code, tr.employee_id,
           e.full_name AS employee_name, e.department, e.manager_id AS owner_manager_id,
           tr.destination, tr.start_date, tr.end_date, tr.purpose,
           tr.approval_status, tr.trip_state, tr.created_on,
           tr.completion_type, cb.full_name AS completed_by_name, tr.completed_at,
           tr.created_at, tr.updated_at
    FROM travel_requests AS tr
    JOIN employees AS e ON e.employee_id = tr.employee_id
    LEFT JOIN employees AS cb ON cb.employee_id = tr.completed_by
"""

# Card rows for My Trips and the manager queues: trip + ticket counts + claimed total.
# total_claimed ignores REJECTED tickets (final, never paid; a replacement ticket is counted instead).
_TRIP_LIST_SELECT = """
    SELECT tr.trip_id, tr.trip_code, e.full_name AS employee_name, tr.destination,
           tr.start_date, tr.end_date, tr.approval_status, tr.trip_state,
           COALESCE(k.ticket_count, 0) AS ticket_count,
           COALESCE(k.pending_ticket_count, 0) AS pending_ticket_count,
           COALESCE(k.total_claimed, 0) AS total_claimed
    FROM travel_requests AS tr
    JOIN employees AS e ON e.employee_id = tr.employee_id
    LEFT JOIN LATERAL (
        SELECT count(*) AS ticket_count,
               count(*) FILTER (WHERE t.status = 'PENDING') AS pending_ticket_count,
               sum(t.total_amount) FILTER (WHERE t.status <> 'REJECTED') AS total_claimed
        FROM expense_tickets AS t
        WHERE t.trip_id = tr.trip_id
    ) AS k ON TRUE
"""


def create(db: Connection, employee_id: int, request: TripCreate) -> dict:
    """Insert a travel request (DB defaults: IN_PROGRESS, created_on = today) and return it."""
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
    return get(db, trip_id)


def get(db: Connection, trip_id: int, *, for_update: bool = False) -> dict | None:
    """One trip; for_update locks the travel_requests row until the transaction ends."""
    lock = " FOR UPDATE OF tr" if for_update else ""
    row = db.execute(
        text(_TRIP_SELECT + " WHERE tr.trip_id = :trip_id" + lock),
        {"trip_id": trip_id},
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


def update_details(db: Connection, trip_id: int, request: TripUpdate) -> None:
    """Replace the editable fields of an In Progress trip (updated_at is set by trigger)."""
    db.execute(
        text(
            """
            UPDATE travel_requests
            SET destination = :destination, start_date = :start_date,
                end_date = :end_date, purpose = :purpose
            WHERE trip_id = :trip_id
            """
        ),
        {
            "trip_id": trip_id,
            "destination": request.destination,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "purpose": request.purpose,
        },
    )


def set_decision(db: Connection, trip_id: int, approved: bool) -> None:
    """Approve -> APPROVED + ACTIVE; reject -> REJECTED (trip_state stays NULL)."""
    db.execute(
        text(
            """
            UPDATE travel_requests
            SET approval_status = CASE WHEN :approved THEN 'APPROVED' ELSE 'REJECTED' END,
                trip_state = CASE WHEN :approved THEN 'ACTIVE' ELSE NULL END
            WHERE trip_id = :trip_id
            """
        ),
        {"trip_id": trip_id, "approved": approved},
    )


def complete_by_manager(db: Connection, trip_id: int, manager_id: int) -> None:
    """Manager completion: COMPLETED, completion_type MANAGER, completed_by, completed_at."""
    db.execute(
        text(
            """
            UPDATE travel_requests
            SET trip_state = 'COMPLETED', completion_type = 'MANAGER',
                completed_by = :manager_id, completed_at = now()
            WHERE trip_id = :trip_id
            """
        ),
        {"trip_id": trip_id, "manager_id": manager_id},
    )


def auto_complete_due(
    db: Connection,
    today: date,
    days_after_start: int,
    trip_id: int | None = None,
) -> int:
    """Complete (AUTO) every Active trip whose start date + days_after_start is today or earlier.
    trip_id limits it to one trip (the check that runs before each ticket creation)."""
    result = db.execute(
        text(
            """
            UPDATE travel_requests
            SET trip_state = 'COMPLETED', completion_type = 'AUTO', completed_at = now()
            WHERE approval_status = 'APPROVED'
              AND trip_state = 'ACTIVE'
              AND start_date + CAST(:days_after_start AS INT) <= :today
              AND (CAST(:trip_id AS INT) IS NULL OR trip_id = :trip_id)
            """
        ),
        {"today": today, "days_after_start": days_after_start, "trip_id": trip_id},
    )
    return result.rowcount


def list_for_employee(db: Connection, employee_id: int, when: str, today: date) -> list[dict]:
    """My Trips. upcoming = ends today or later; past = ended before today; all = everything."""
    filters = {
        "upcoming": (" AND tr.end_date >= :today", " ORDER BY tr.start_date ASC, tr.trip_id ASC"),
        "past": (" AND tr.end_date < :today", " ORDER BY tr.start_date DESC, tr.trip_id DESC"),
        "all": ("", " ORDER BY tr.start_date DESC, tr.trip_id DESC"),
    }
    where_extra, order_by = filters[when]
    rows = db.execute(
        text(_TRIP_LIST_SELECT + " WHERE tr.employee_id = :employee_id" + where_extra + order_by),
        {"employee_id": employee_id, "today": today},
    ).mappings().all()
    return [dict(row) for row in rows]


def list_pending_for_manager(db: Connection, manager_id: int) -> list[dict]:
    """Trip requests tab: In Progress trips of the manager's direct reports, soonest start first."""
    rows = db.execute(
        text(
            _TRIP_LIST_SELECT
            + """
            WHERE e.manager_id = :manager_id AND tr.approval_status = 'IN_PROGRESS'
            ORDER BY tr.start_date ASC, tr.trip_id ASC
            """
        ),
        {"manager_id": manager_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def list_to_complete_for_manager(db: Connection, manager_id: int, today: date) -> list[dict]:
    """Trips to complete tab: Active trips of direct reports whose end date has been reached."""
    rows = db.execute(
        text(
            _TRIP_LIST_SELECT
            + """
            WHERE e.manager_id = :manager_id
              AND tr.approval_status = 'APPROVED' AND tr.trip_state = 'ACTIVE'
              AND tr.end_date <= :today
            ORDER BY tr.end_date ASC, tr.trip_id ASC
            """
        ),
        {"manager_id": manager_id, "today": today},
    ).mappings().all()
    return [dict(row) for row in rows]

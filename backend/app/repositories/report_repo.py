"""
The three demo queries from database/queries/demo_queries.sql, plus the employee dashboard queries.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.repositories.trip_repo import _TRIP_LIST_SELECT   # the same card query as My Trips


def trip_expenses(db: Connection, manager_id: int) -> list[dict]:
    """SQL demo 1: join employees + trips + expenses (TripExpenseJoinRow)."""
    rows = db.execute(
        text(
            """
            SELECT e.full_name AS employee_name, t.trip_code, t.destination,
                   x.expense_code, x.expense_type, x.amount, x.status
            FROM expenses x
            JOIN travel_requests t ON t.trip_id = x.trip_id
            JOIN employees e       ON e.employee_id = t.employee_id
            WHERE e.manager_id = :manager_id
            ORDER BY t.trip_code, x.expense_code
            """
        ),
        {"manager_id": manager_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def spend_by_trip_category(db: Connection, manager_id: int) -> list[dict]:
    """SQL demo 2: approved money by trip and category, plus a trip total row
    (expense_type NULL) from GROUPING SETS (SpendByTripCategoryRow)."""
    rows = db.execute(
        text(
            """
            SELECT t.trip_code, t.destination, x.expense_type,
                   COUNT(*) AS line_count, SUM(x.amount) AS total_amount
            FROM expenses x
            JOIN travel_requests t ON t.trip_id = x.trip_id
            JOIN employees e       ON e.employee_id = t.employee_id
            WHERE x.status IN ('APPROVED','AUTO_APPROVED') AND e.manager_id = :manager_id
            GROUP BY GROUPING SETS ((t.trip_code, t.destination, x.expense_type), (t.trip_code, t.destination))
            ORDER BY t.trip_code, x.expense_type NULLS LAST
            """
        ),
        {"manager_id": manager_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def pending_flagged_expenses(db: Connection, manager_id: int) -> list[dict]:
    """SQL demo 3: flagged lines inside PENDING tickets (PendingExpenseOut; expense_id and ticket_id
    added so the page can link each row; k.ticket_id is already in GROUP BY, so the rows are unchanged)."""
    rows = db.execute(
        text(
            """
            SELECT x.expense_id, x.expense_code, k.ticket_id, k.ticket_code, t.trip_code,
                   e.full_name AS employee_name, t.destination,
                   x.expense_type, x.amount, ARRAY_AGG(f.rule_code ORDER BY f.rule_code) AS flag_codes,
                   k.submitted_at
            FROM expenses x
            JOIN expense_tickets k ON k.ticket_id = x.ticket_id
            JOIN travel_requests t ON t.trip_id = x.trip_id
            JOIN employees e       ON e.employee_id = t.employee_id
            JOIN policy_flags f    ON f.expense_id = x.expense_id
            WHERE k.status = 'PENDING' AND e.manager_id = :manager_id
            GROUP BY x.expense_id, k.ticket_id, t.trip_id, e.employee_id
            ORDER BY k.submitted_at
            """
        ),
        {"manager_id": manager_id},
    ).mappings().all()
    return [dict(row) for row in rows]


# --- Employee dashboard (GET /dashboard/employee): one employee's OWN rows only ---
def employee_dashboard_totals(db: Connection, employee_id: int) -> dict:
    """Trip counts by status + money claimed (REJECTED tickets excluded, as on My Trips)."""
    row = db.execute(
        text(
            """
            SELECT count(*) AS total_trips,
                   count(*) FILTER (WHERE tr.approval_status = 'APPROVED' AND tr.trip_state = 'ACTIVE') AS open_trips,
                   count(*) FILTER (WHERE tr.approval_status = 'IN_PROGRESS') AS pending_trip_approval,
                   (SELECT COALESCE(sum(k.total_amount), 0)
                    FROM expense_tickets k
                    WHERE k.employee_id = :employee_id AND k.status <> 'REJECTED') AS total_claimed
            FROM travel_requests tr
            WHERE tr.employee_id = :employee_id
            """
        ),
        {"employee_id": employee_id},
    ).mappings().one()
    return dict(row)


def employee_spend_by_category(db: Connection, employee_id: int) -> list[dict]:
    """Line amounts per category in the employee's tickets that are not REJECTED, biggest first."""
    rows = db.execute(
        text(
            """
            SELECT x.expense_type, SUM(x.amount) AS total_amount
            FROM expenses x
            JOIN expense_tickets k ON k.ticket_id = x.ticket_id
            WHERE k.employee_id = :employee_id AND k.status <> 'REJECTED'
            GROUP BY x.expense_type
            ORDER BY total_amount DESC, x.expense_type
            """
        ),
        {"employee_id": employee_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def employee_recent_trips(db: Connection, employee_id: int, limit: int) -> list[dict]:
    """The employee's newest trip requests (by request date), as My Trips card rows."""
    rows = db.execute(
        text(
            _TRIP_LIST_SELECT
            + """
            WHERE tr.employee_id = :employee_id
            ORDER BY tr.created_on DESC, tr.trip_id DESC
            LIMIT CAST(:limit AS INT)
            """
        ),
        {"employee_id": employee_id, "limit": limit},
    ).mappings().all()
    return [dict(row) for row in rows]

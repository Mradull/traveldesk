"""
The three demo queries from database/queries/demo_queries.sql.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection


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
    """SQL demo 3: flagged lines inside PENDING tickets (PendingExpenseOut; expense_id added)."""
    rows = db.execute(
        text(
            """
            SELECT x.expense_id, x.expense_code, k.ticket_code, t.trip_code,
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

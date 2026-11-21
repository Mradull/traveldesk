"""
SQL for expense_tickets and policy_flags.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Connection

# One ticket row as shown in lists (TicketSummaryOut) plus the extra fields used by detail,
# the manager queue and permission checks (owner, owner's manager, trip state).
_TICKET_SELECT = """
    SELECT k.ticket_id, k.ticket_code, k.trip_id, t.trip_code, k.status, k.routing,
           k.line_count, k.flag_count, k.total_amount, k.submitted_at, k.decided_at,
           (k.status <> 'PENDING') AS is_read_only,
           original.ticket_code AS replacement_of_ticket_code,
           replacement.ticket_code AS replaced_by_ticket_code,
           k.replacement_of_ticket_id,
           t.destination, k.employee_id, e.full_name AS employee_name,
           e.manager_id AS owner_manager_id,
           t.approval_status AS trip_approval_status, t.trip_state, t.start_date AS trip_start_date,
           ARRAY(
               SELECT DISTINCT f.rule_code
               FROM policy_flags AS f
               JOIN expenses AS x ON x.expense_id = f.expense_id
               WHERE x.ticket_id = k.ticket_id
               ORDER BY f.rule_code
           ) AS flag_codes
    FROM expense_tickets AS k
    JOIN travel_requests AS t ON t.trip_id = k.trip_id
    JOIN employees AS e ON e.employee_id = k.employee_id
    LEFT JOIN expense_tickets AS original ON original.ticket_id = k.replacement_of_ticket_id
    LEFT JOIN expense_tickets AS replacement ON replacement.replacement_of_ticket_id = k.ticket_id
"""


def get(db: Connection, ticket_id: int) -> dict | None:
    """One ticket with its trip, owner and replacement links."""
    row = db.execute(
        text(_TICKET_SELECT + " WHERE k.ticket_id = :ticket_id"),
        {"ticket_id": ticket_id},
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


def lock(db: Connection, ticket_id: int) -> dict | None:
    """SELECT ... FOR UPDATE on the ticket row (decisions and replacement checks)."""
    row = db.execute(
        text(
            """
            SELECT k.ticket_id, k.trip_id, k.employee_id, k.status, e.manager_id AS owner_manager_id
            FROM expense_tickets AS k
            JOIN employees AS e ON e.employee_id = k.employee_id
            WHERE k.ticket_id = :ticket_id
            FOR UPDATE OF k
            """
        ),
        {"ticket_id": ticket_id},
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


def is_replaced(db: Connection, ticket_id: int) -> bool:
    """True when a newer ticket already names this one in replacement_of_ticket_id."""
    return db.execute(
        text("SELECT EXISTS (SELECT 1 FROM expense_tickets WHERE replacement_of_ticket_id = :ticket_id)"),
        {"ticket_id": ticket_id},
    ).scalar_one()


def insert(
    db: Connection,
    *,
    trip_id: int,
    employee_id: int,
    replacement_of_ticket_id: int | None,
    status: str,
    routing: str,
    line_count: int,
    flag_count: int,
    total_amount: Decimal,
) -> int:
    """Insert the ticket with its final routing; decided_at is set only for AUTO_APPROVED."""
    return db.execute(
        text(
            """
            INSERT INTO expense_tickets
                (trip_id, employee_id, replacement_of_ticket_id, status, routing,
                 line_count, flag_count, total_amount, decided_at)
            VALUES
                (:trip_id, :employee_id, :replacement_of_ticket_id, :status, :routing,
                 :line_count, :flag_count, :total_amount,
                 CASE WHEN :status = 'PENDING' THEN NULL ELSE now() END)
            RETURNING ticket_id
            """
        ),
        {
            "trip_id": trip_id,
            "employee_id": employee_id,
            "replacement_of_ticket_id": replacement_of_ticket_id,
            "status": status,
            "routing": routing,
            "line_count": line_count,
            "flag_count": flag_count,
            "total_amount": total_amount,
        },
    ).scalar_one()


def set_decided(db: Connection, ticket_id: int, status: str) -> None:
    """PENDING -> APPROVED / REJECTED (the only change the immutability trigger allows)."""
    db.execute(
        text("UPDATE expense_tickets SET status = :status, decided_at = now() WHERE ticket_id = :ticket_id"),
        {"ticket_id": ticket_id, "status": status},
    )


def insert_flag(
    db: Connection,
    expense_id: int,
    rule_code: str,
    message: str,
    policy_ref: str,
    threshold_amount: Decimal | None,
    rules_version: str,
) -> None:
    """One policy flag on one expense line."""
    db.execute(
        text(
            """
            INSERT INTO policy_flags
                (expense_id, rule_code, message, policy_ref, threshold_amount, rules_version)
            VALUES
                (:expense_id, :rule_code, :message, :policy_ref, :threshold_amount, :rules_version)
            """
        ),
        {
            "expense_id": expense_id,
            "rule_code": rule_code,
            "message": message,
            "policy_ref": policy_ref,
            "threshold_amount": threshold_amount,
            "rules_version": rules_version,
        },
    )


def list_for_employee(
    db: Connection,
    employee_id: int,
    status: str | None = None,
    trip_id: int | None = None,
) -> list[dict]:
    """Expense Management: the caller's tickets across trips, optional status / trip filters."""
    rows = db.execute(
        text(
            _TICKET_SELECT
            + """
            WHERE k.employee_id = :employee_id
              AND (CAST(:status AS TEXT) IS NULL OR k.status = :status)
              AND (CAST(:trip_id AS INT) IS NULL OR k.trip_id = :trip_id)
            ORDER BY k.submitted_at DESC, k.ticket_id DESC
            """
        ),
        {"employee_id": employee_id, "status": status, "trip_id": trip_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def list_for_trip(db: Connection, trip_id: int) -> list[dict]:
    """All tickets of one trip (Trip Detail, GET /trips/{id}/tickets)."""
    rows = db.execute(
        text(_TICKET_SELECT + " WHERE k.trip_id = :trip_id ORDER BY k.submitted_at, k.ticket_id"),
        {"trip_id": trip_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def list_pending_for_manager(db: Connection, manager_id: int) -> list[dict]:
    """Expense tickets tab: PENDING tickets of direct reports, oldest first."""
    rows = db.execute(
        text(
            _TICKET_SELECT
            + """
            WHERE e.manager_id = :manager_id AND k.status = 'PENDING'
            ORDER BY k.submitted_at, k.ticket_id
            """
        ),
        {"manager_id": manager_id},
    ).mappings().all()
    return [dict(row) for row in rows]

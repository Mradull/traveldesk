"""
SQL for expenses.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

# Expense line + its photo code + who owns it (for permission checks).
_EXPENSE_SELECT = """
    SELECT x.expense_id, x.expense_code, x.ticket_id, x.trip_id, x.expense_type, x.amount,
           x.currency, x.expense_date, x.description, x.evidence_id, v.evidence_code,
           v.sha256, x.invoice_number, x.status, x.created_at,
           k.employee_id, e.manager_id AS owner_manager_id
    FROM expenses AS x
    JOIN expense_evidence AS v ON v.evidence_id = x.evidence_id
    JOIN expense_tickets AS k ON k.ticket_id = x.ticket_id
    JOIN employees AS e ON e.employee_id = k.employee_id
"""


def insert(
    db: Connection,
    *,
    ticket_id: int,
    trip_id: int,
    evidence_id: UUID,
    expense_type: str,
    amount: Decimal,
    expense_date: date,
    description: str,
    invoice_number: str | None,
    status: str,
) -> int:
    """Insert one expense line (attaching its photo) and return the new expense_id."""
    return db.execute(
        text(
            """
            INSERT INTO expenses
                (ticket_id, trip_id, evidence_id, expense_type, amount, expense_date,
                 description, invoice_number, status)
            VALUES
                (:ticket_id, :trip_id, :evidence_id, :expense_type, :amount, :expense_date,
                 :description, :invoice_number, :status)
            RETURNING expense_id
            """
        ),
        {
            "ticket_id": ticket_id,
            "trip_id": trip_id,
            "evidence_id": evidence_id,
            "expense_type": expense_type,
            "amount": amount,
            "expense_date": expense_date,
            "description": description,
            "invoice_number": invoice_number,
            "status": status,
        },
    ).scalar_one()


def get(db: Connection, expense_id: int) -> dict | None:
    """One expense line with its owner."""
    row = db.execute(
        text(_EXPENSE_SELECT + " WHERE x.expense_id = :expense_id"),
        {"expense_id": expense_id},
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


def list_for_ticket(db: Connection, ticket_id: int) -> list[dict]:
    """Lines of one ticket in EXP order."""
    rows = db.execute(
        text(_EXPENSE_SELECT + " WHERE x.ticket_id = :ticket_id ORDER BY x.expense_id"),
        {"ticket_id": ticket_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def list_for_trip(db: Connection, trip_id: int) -> list[dict]:
    """All lines of one trip (GET /trips/{id}/expenses)."""
    rows = db.execute(
        text(_EXPENSE_SELECT + " WHERE x.trip_id = :trip_id ORDER BY x.expense_id"),
        {"trip_id": trip_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def set_status_for_ticket(db: Connection, ticket_id: int, status: str) -> None:
    """Lines mirror their ticket; called BEFORE the ticket itself changes (immutability trigger)."""
    db.execute(
        text("UPDATE expenses SET status = :status WHERE ticket_id = :ticket_id"),
        {"ticket_id": ticket_id, "status": status},
    )


def flags_for_expenses(db: Connection, expense_ids: list[int]) -> dict[int, list[dict]]:
    """Stored policy flags grouped by expense_id."""
    if not expense_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT expense_id, rule_code, message, policy_ref, threshold_amount
            FROM policy_flags
            WHERE expense_id = ANY(:expense_ids)
            ORDER BY expense_id, rule_code
            """
        ),
        {"expense_ids": expense_ids},
    ).mappings().all()
    grouped: dict[int, list[dict]] = {expense_id: [] for expense_id in expense_ids}
    for row in rows:
        grouped[row["expense_id"]].append(dict(row))
    return grouped


def existing_receipts(
    db: Connection,
    employee_id: int,
    before_expense_id: int | None = None,
) -> tuple[set[str], set[str]]:
    """Photo hashes and (upper-case) invoice numbers already claimed by this employee on tickets
    that are NOT rejected [POL-7.4]. before_expense_id limits it to lines submitted earlier, so a
    re-check of one line gives the same answer as at submission."""
    rows = db.execute(
        text(
            """
            SELECT v.sha256, upper(x.invoice_number) AS invoice_number
            FROM expenses AS x
            JOIN expense_evidence AS v ON v.evidence_id = x.evidence_id
            JOIN expense_tickets AS k ON k.ticket_id = x.ticket_id
            WHERE k.employee_id = :employee_id
              AND k.status <> 'REJECTED'
              AND (CAST(:before_expense_id AS INT) IS NULL OR x.expense_id < :before_expense_id)
            """
        ),
        {"employee_id": employee_id, "before_expense_id": before_expense_id},
    ).mappings().all()
    hashes = {row["sha256"] for row in rows}
    invoices = {row["invoice_number"] for row in rows if row["invoice_number"]}
    return hashes, invoices

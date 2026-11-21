"""
SQL for trip_approvals and ticket_approvals (insert only; rows are immutable).

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection


def insert_trip_approval(
    db: Connection,
    trip_id: int,
    reviewer_id: int,
    decision: str,
    review_comment: str | None,
) -> None:
    """One permanent decision row per trip (UNIQUE trip_id is the backstop for a second decision)."""
    db.execute(
        text(
            """
            INSERT INTO trip_approvals (trip_id, reviewer_id, decision, review_comment)
            VALUES (:trip_id, :reviewer_id, :decision, :review_comment)
            """
        ),
        {
            "trip_id": trip_id,
            "reviewer_id": reviewer_id,
            "decision": decision,
            "review_comment": review_comment,
        },
    )


def list_trip_approvals(db: Connection, trip_id: int) -> list[dict]:
    """Decision history of a trip with the reviewer's name (TripApprovalOut)."""
    rows = db.execute(
        text(
            """
            SELECT a.approval_id, a.trip_id, a.reviewer_id, e.full_name AS reviewer_name,
                   a.decision, a.review_comment, a.decided_at
            FROM trip_approvals AS a
            JOIN employees AS e ON e.employee_id = a.reviewer_id
            WHERE a.trip_id = :trip_id
            ORDER BY a.decided_at, a.approval_id
            """
        ),
        {"trip_id": trip_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def insert_ticket_approval(
    db: Connection,
    ticket_id: int,
    reviewer_type: str,
    reviewer_id: int | None,
    decision: str,
    rejection_reason: str | None,
    review_comment: str | None,
) -> None:
    """One permanent decision row per ticket: MANAGER decision or SYSTEM auto-approval."""
    db.execute(
        text(
            """
            INSERT INTO ticket_approvals
                (ticket_id, reviewer_type, reviewer_id, decision, rejection_reason, review_comment)
            VALUES
                (:ticket_id, :reviewer_type, :reviewer_id, :decision, :rejection_reason, :review_comment)
            """
        ),
        {
            "ticket_id": ticket_id,
            "reviewer_type": reviewer_type,
            "reviewer_id": reviewer_id,
            "decision": decision,
            "rejection_reason": rejection_reason,
            "review_comment": review_comment,
        },
    )


def list_ticket_approvals(db: Connection, ticket_id: int) -> list[dict]:
    """Decision history of a ticket (TicketApprovalOut); reviewer_name is 'SYSTEM' for auto-approval."""
    rows = db.execute(
        text(
            """
            SELECT a.approval_id, a.ticket_id, a.reviewer_type, a.reviewer_id,
                   COALESCE(e.full_name, 'SYSTEM') AS reviewer_name,
                   a.decision, a.rejection_reason, a.review_comment, a.decided_at
            FROM ticket_approvals AS a
            LEFT JOIN employees AS e ON e.employee_id = a.reviewer_id
            WHERE a.ticket_id = :ticket_id
            ORDER BY a.decided_at, a.approval_id
            """
        ),
        {"ticket_id": ticket_id},
    ).mappings().all()
    return [dict(row) for row in rows]

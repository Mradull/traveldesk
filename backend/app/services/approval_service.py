"""
decide_trip and decide_ticket with SELECT ... FOR UPDATE; review_comment (10+ chars to reject),
rejection_reason for tickets; ticket lines updated before the ticket (immutability trigger).

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0

Spec references: Business rules > Manager decision; Transactions; US-08, US-14, US-15.
The 10-character comment and the reason/comment combinations are already enforced by
schemas.TripDecisionRequest / TicketDecisionRequest (422) and again by database CHECKs.
"""

from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.repositories import approval_repo, expense_repo, ticket_repo, trip_repo
from app.schemas import (
    ApprovalStatus,
    CurrentUser,
    Decision,
    ErrorCode,
    ReviewerType,
    TicketDecisionRequest,
    TicketDetailOut,
    TicketStatus,
    TripDecisionRequest,
    TripOut,
    today,
)
from app.services import ticket_service, trip_service

_ALREADY_DECIDED_MESSAGE = "This record has already been decided."


def _clean_comment(comment: str | None) -> str | None:
    """Store a blank optional comment as NULL."""
    return comment.strip() if comment and comment.strip() else None


def decide_trip(
    db: Connection,
    manager: CurrentUser,
    trip_id: int,
    request: TripDecisionRequest,
) -> TripOut:
    """US-08: approve (-> Approved - Active) or reject (-> Rejected, comment required) a trip request.

    One transaction: lock the trip row, check the caller manages the owner, check IN_PROGRESS and
    the approval window (today < start date + 90 days), update the trip, insert trip_approvals.
    """
    trip = trip_repo.get(db, trip_id, for_update=True)
    if trip is None:
        raise AppError(ErrorCode.NOT_FOUND, 404, "Trip not found.")
    if trip_service.is_owner(manager, trip):
        raise AppError(ErrorCode.SELF_APPROVAL, 403, "You cannot decide your own trip request.")
    if not trip_service.is_approving_manager(manager, trip):
        raise AppError(ErrorCode.NOT_FOUND, 404, "Trip not found.")
    if trip["approval_status"] != ApprovalStatus.IN_PROGRESS:
        raise AppError(ErrorCode.ALREADY_DECIDED, 409, _ALREADY_DECIDED_MESSAGE)
    if today() >= trip_service.auto_complete_on(trip["start_date"]):
        raise AppError(
            ErrorCode.TRIP_APPROVAL_WINDOW_PASSED,
            409,
            "This request can no longer be decided: its start date was more than 90 days ago.",
        )

    approved = request.decision == Decision.APPROVED
    trip_repo.set_decision(db, trip_id, approved)
    try:
        approval_repo.insert_trip_approval(
            db, trip_id, manager.employee_id, request.decision.value, _clean_comment(request.review_comment)
        )
    except IntegrityError as exc:                       # UNIQUE(trip_id): a parallel second decision
        raise AppError(ErrorCode.ALREADY_DECIDED, 409, _ALREADY_DECIDED_MESSAGE) from exc

    result = trip_service.to_trip_out(trip_repo.get(db, trip_id), manager)
    db.commit()
    return result


def decide_ticket(
    db: Connection,
    manager: CurrentUser,
    ticket_id: int,
    request: TicketDecisionRequest,
) -> TicketDetailOut:
    """US-14: approve (comment optional) or reject (reason + 10-character comment) a PENDING ticket.

    One transaction: SELECT ... FOR UPDATE on the ticket, check PENDING and that the caller manages
    the owner, update the expense LINES first and the ticket LAST (the migration 006 trigger only
    allows line changes while the ticket is still PENDING), insert ticket_approvals.
    Already-pending tickets of a completed trip are still decided (spec trip lifecycle).
    """
    ticket = ticket_repo.lock(db, ticket_id)
    if ticket is None:
        raise AppError(ErrorCode.NOT_FOUND, 404, "Ticket not found.")
    if ticket["employee_id"] == manager.employee_id:
        raise AppError(ErrorCode.SELF_APPROVAL, 403, "You cannot decide your own ticket.")
    if ticket["owner_manager_id"] != manager.employee_id:
        raise AppError(ErrorCode.NOT_FOUND, 404, "Ticket not found.")
    if ticket["status"] != TicketStatus.PENDING:
        raise AppError(ErrorCode.ALREADY_DECIDED, 409, _ALREADY_DECIDED_MESSAGE)

    new_status = TicketStatus.APPROVED if request.decision == Decision.APPROVED else TicketStatus.REJECTED
    expense_repo.set_status_for_ticket(db, ticket_id, new_status.value)     # lines first
    ticket_repo.set_decided(db, ticket_id, new_status.value)                # ticket last
    try:
        approval_repo.insert_ticket_approval(
            db,
            ticket_id,
            ReviewerType.MANAGER.value,
            manager.employee_id,
            request.decision.value,
            request.rejection_reason.value if request.rejection_reason else None,
            _clean_comment(request.review_comment),
        )
    except IntegrityError as exc:                       # UNIQUE(ticket_id) backstop
        raise AppError(ErrorCode.ALREADY_DECIDED, 409, _ALREADY_DECIDED_MESSAGE) from exc

    result = ticket_service.build_detail(db, manager, ticket_id)
    db.commit()
    return result

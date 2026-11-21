"""
One-transaction ticket create: trip Active + not past auto-complete, evidence owner/unattached,
expense_date >= trip created_on (422 on expenses.<n>.expense_date), policy engine, routing, SYSTEM approval, replacement rules.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0

Also the read side of expense tickets and lines (Expense Management, Ticket Detail, manager queue,
per-line policy re-check). Spec references: Business rules > Expense tickets, decisions and
replacements; Transactions; US-11, US-12, US-13, US-16, US-18.
"""

from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.errors import AppError
from app.repositories import approval_repo, evidence_repo, expense_repo, ticket_repo, trip_repo
from app.schemas import (
    ApprovalStatus,
    CurrentUser,
    ErrorCode,
    ExpenseOut,
    PendingTicketOut,
    PolicyCheckOut,
    PolicyFlag,
    ReviewerType,
    Role,
    TicketApprovalOut,
    TicketCreate,
    TicketDecisionValue,
    TicketDetailOut,
    TicketStatus,
    TicketSummaryOut,
    TripState,
    today,
)
from app.services import policy_engine, trip_service

_TICKET_NOT_FOUND = "Ticket not found."
_EXPENSE_NOT_FOUND = "Expense not found."


# ----------------------------------------------------------------------------- helpers
def _can_view(user: CurrentUser, row: dict) -> bool:
    """Owner, or the owner's line manager (spec: 'Owner or approver'); everyone else gets 404."""
    return user.employee_id == row["employee_id"] or (
        user.role == Role.MANAGER and row["owner_manager_id"] == user.employee_id
    )


def _expense_out(row: dict, flags: list[dict]) -> ExpenseOut:
    return ExpenseOut(**row, flags=[PolicyFlag(**flag) for flag in flags])


def _expenses_out(db: Connection, rows: list[dict]) -> list[ExpenseOut]:
    flags = expense_repo.flags_for_expenses(db, [row["expense_id"] for row in rows])
    return [_expense_out(row, flags.get(row["expense_id"], [])) for row in rows]


def build_detail(db: Connection, user: CurrentUser, ticket_id: int) -> TicketDetailOut:
    """TicketDetailOut: lines with flags, decision history, replacement links, can_create_replacement."""
    ticket = ticket_repo.get(db, ticket_id)
    if ticket is None or not _can_view(user, ticket):
        raise AppError(ErrorCode.NOT_FOUND, 404, _TICKET_NOT_FOUND)
    trip_still_active = (
        ticket["trip_approval_status"] == ApprovalStatus.APPROVED
        and ticket["trip_state"] == TripState.ACTIVE
        and today() < trip_service.auto_complete_on(ticket["trip_start_date"])
    )
    can_replace = (
        user.employee_id == ticket["employee_id"]
        and ticket["status"] == TicketStatus.REJECTED
        and ticket["replaced_by_ticket_code"] is None
        and trip_still_active
    )
    return TicketDetailOut(
        **ticket,
        expenses=_expenses_out(db, expense_repo.list_for_ticket(db, ticket_id)),
        history=[TicketApprovalOut(**row) for row in approval_repo.list_ticket_approvals(db, ticket_id)],
        can_create_replacement=can_replace,
    )


# ----------------------------------------------------------------------------- US-11 / US-12 / US-16 create
def create_ticket(db: Connection, employee: CurrentUser, trip_id: int, request: TicketCreate) -> TicketDetailOut:
    """Raise a ticket (1-20 lines, a receipt photo on each) on an Approved - Active trip.

    Steps (spec > Transactions): auto-complete check; lock the trip and check it is Active;
    replacement rules; expense-date rule; lock the photos and check owner + unattached; run the
    policy engine; insert ticket, lines and flags; SYSTEM approval when clean. Any failure rolls
    everything back (nothing is committed until the end).
    """
    settings = get_settings()

    # 1. Same check as the hourly job, run right now so nothing slips in between runs [POL-4.3].
    #    Committed on its own: the completion stands even if this ticket is then refused.
    trip_repo.auto_complete_due(db, today(), trip_service.auto_complete_days(), trip_id)
    db.commit()

    # 2. Lock the trip; only the owner's Approved - Active trip accepts tickets [POL-5.2].
    trip = trip_repo.get(db, trip_id, for_update=True)
    if trip is None or not trip_service.is_owner(employee, trip):
        raise AppError(ErrorCode.NOT_FOUND, 404, "Trip not found.")
    if trip["approval_status"] != ApprovalStatus.APPROVED or trip["trip_state"] != TripState.ACTIVE:
        raise AppError(
            ErrorCode.TRIP_NOT_ACTIVE, 409, "Tickets can only be raised on an Approved - Active trip."
        )

    # 3. Replacement: the caller's own REJECTED ticket on this trip, not replaced before [POL-5.8].
    replaced_id = request.replacement_of_ticket_id
    if replaced_id is not None:
        original = ticket_repo.lock(db, replaced_id)
        if (
            original is None
            or original["employee_id"] != employee.employee_id
            or original["trip_id"] != trip_id
            or original["status"] != TicketStatus.REJECTED
            or ticket_repo.is_replaced(db, replaced_id)
        ):
            raise AppError(
                ErrorCode.REPLACEMENT_NOT_ALLOWED,
                409,
                "Only your own rejected ticket on this trip can be replaced, and only once.",
            )

    # 4. Expense date on/after the trip's creation date [POL-8.2], reported under each line's date.
    created_on = trip["created_on"]
    early_lines = [i for i, line in enumerate(request.expenses) if line.expense_date < created_on]
    if early_lines:
        raise AppError(
            ErrorCode.EXPENSE_DATE_BEFORE_TRIP_CREATED,
            422,
            "Expense date is before this trip was created",
            details=[
                {"field": f"expenses.{i}.expense_date", "msg": f"Must be on or after {created_on.isoformat()}"}
                for i in early_lines
            ],
        )

    # 5. Photos: each must be the caller's own upload (404) and not attached to another line (409).
    photos = evidence_repo.lock_for_ticket(db, [line.evidence_id for line in request.expenses])
    not_found = [
        i
        for i, line in enumerate(request.expenses)
        if line.evidence_id not in photos or photos[line.evidence_id]["employee_id"] != employee.employee_id
    ]
    if not_found:
        raise AppError(
            ErrorCode.EVIDENCE_NOT_FOUND,
            404,
            "Receipt photo not found. Upload the photo again.",
            details=[{"field": f"expenses.{i}.evidence_id", "msg": "Receipt photo not found"} for i in not_found],
        )
    used = [i for i, line in enumerate(request.expenses) if photos[line.evidence_id]["is_attached"]]
    if used:
        raise AppError(
            ErrorCode.EVIDENCE_ALREADY_USED,
            409,
            "A receipt photo is already attached to another expense line. Upload a new photo.",
            details=[{"field": f"expenses.{i}.evidence_id", "msg": "Photo already used"} for i in used],
        )

    # 6. Policy engine on every line. Earlier lines of this same ticket also count as "already
    #    claimed", so the same photo uploaded twice in one ticket is flagged on the second line.
    config = policy_engine.PolicyConfig.from_settings(settings)
    hashes, invoices = expense_repo.existing_receipts(db, employee.employee_id)
    line_flags: list[list[PolicyFlag]] = []
    for line in request.expenses:
        sha256 = photos[line.evidence_id]["sha256"]
        line_flags.append(
            policy_engine.evaluate_line(
                policy_engine.PolicyLine(line.expense_type, line.amount, sha256, line.invoice_number),
                config,
                hashes,
                invoices,
            )
        )
        hashes.add(sha256)
        if line.invoice_number:
            invoices.add(line.invoice_number.upper())
    flag_count = sum(len(flags) for flags in line_flags)
    status, routing = policy_engine.route(flag_count)

    # 7. Insert ticket, lines (attaching the photos) and flags; SYSTEM approval when clean [POL-9.2].
    try:
        ticket_id = ticket_repo.insert(
            db,
            trip_id=trip_id,
            employee_id=employee.employee_id,
            replacement_of_ticket_id=replaced_id,
            status=status.value,
            routing=routing.value,
            line_count=len(request.expenses),
            flag_count=flag_count,
            total_amount=sum(line.amount for line in request.expenses),
        )
        for line, flags in zip(request.expenses, line_flags):
            expense_id = expense_repo.insert(
                db,
                ticket_id=ticket_id,
                trip_id=trip_id,
                evidence_id=line.evidence_id,
                expense_type=line.expense_type.value,
                amount=line.amount,
                expense_date=line.expense_date,
                description=line.description,
                invoice_number=line.invoice_number,
                status=status.value,
            )
            for flag in flags:
                ticket_repo.insert_flag(
                    db,
                    expense_id,
                    flag.rule_code.value,
                    flag.message,
                    flag.policy_ref,
                    flag.threshold_amount,
                    config.rules_version,
                )
        if status == TicketStatus.AUTO_APPROVED:
            approval_repo.insert_ticket_approval(
                db, ticket_id, ReviewerType.SYSTEM.value, None, TicketDecisionValue.AUTO_APPROVED.value, None, None
            )
    except IntegrityError as exc:
        # Backstops for a parallel request using the same photo / replacing the same ticket.
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == "expenses_evidence_id_key":
            raise AppError(ErrorCode.EVIDENCE_ALREADY_USED, 409, "A receipt photo is already in use.") from exc
        if constraint == "expense_tickets_replacement_of_ticket_id_key":
            raise AppError(ErrorCode.REPLACEMENT_NOT_ALLOWED, 409, "This ticket was already replaced.") from exc
        raise

    result = build_detail(db, employee, ticket_id)
    db.commit()
    return result


# ----------------------------------------------------------------------------- US-13 read side
def get_ticket(db: Connection, user: CurrentUser, ticket_id: int) -> TicketDetailOut:
    return build_detail(db, user, ticket_id)


def list_my_tickets(
    db: Connection, employee: CurrentUser, status: TicketStatus | None, trip_id: int | None
) -> list[TicketSummaryOut]:
    """Expense Management: all the caller's tickets, optional status and trip filters."""
    rows = ticket_repo.list_for_employee(
        db, employee.employee_id, status.value if status else None, trip_id
    )
    return [TicketSummaryOut(**row) for row in rows]


def list_trip_tickets(db: Connection, user: CurrentUser, trip_id: int) -> list[TicketSummaryOut]:
    """Tickets of one trip for the owner or approving manager (others 404)."""
    trip_service.visible_trip(db, user, trip_id)
    return [TicketSummaryOut(**row) for row in ticket_repo.list_for_trip(db, trip_id)]


def list_trip_expenses(db: Connection, user: CurrentUser, trip_id: int) -> list[ExpenseOut]:
    """Expense lines of one trip (brief: GET /trips/{id}/expenses kept)."""
    trip_service.visible_trip(db, user, trip_id)
    return _expenses_out(db, expense_repo.list_for_trip(db, trip_id))


def get_expense(db: Connection, user: CurrentUser, expense_id: int) -> ExpenseOut:
    row = expense_repo.get(db, expense_id)
    if row is None or not _can_view(user, row):
        raise AppError(ErrorCode.NOT_FOUND, 404, _EXPENSE_NOT_FOUND)
    return _expenses_out(db, [row])[0]


def policy_check(db: Connection, user: CurrentUser, expense_id: int) -> PolicyCheckOut:
    """US-18: re-run the rules for one line, read-only. Duplicates are compared with lines that
    existed before it (as at submission), so the answer is reproducible."""
    row = expense_repo.get(db, expense_id)
    if row is None or not _can_view(user, row):
        raise AppError(ErrorCode.NOT_FOUND, 404, _EXPENSE_NOT_FOUND)
    config = policy_engine.PolicyConfig.from_settings(get_settings())
    hashes, invoices = expense_repo.existing_receipts(db, row["employee_id"], before_expense_id=expense_id)
    flags = policy_engine.evaluate_line(
        policy_engine.PolicyLine(row["expense_type"], row["amount"], row["sha256"], row["invoice_number"]),
        config,
        hashes,
        invoices,
    )
    return PolicyCheckOut(
        expense_id=row["expense_id"],
        expense_code=row["expense_code"],
        flags=flags,
        requires_manager_review=bool(flags),
        rules_version=config.rules_version,
    )


def list_pending_tickets(db: Connection, manager: CurrentUser) -> list[PendingTicketOut]:
    """Approvals > Expense tickets: PENDING tickets of direct reports with their flag codes."""
    return [PendingTicketOut(**row) for row in ticket_repo.list_pending_for_manager(db, manager.employee_id)]

"""
Trip state machine: create/edit (v2.0 date rules), list/detail with can_* flags, earliest_expense_date (= created_on),
auto_complete_on (= start + 90 days), manager completion on/after end date.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0

Spec references: Business rules > Trip lifecycle / Trip rules; Permission matrix; API endpoints.
Access rule (spec "Users, roles and permissions"): a wrong role is 403 (route guards), but a record
that exists and belongs to someone else is 404, so ids cannot be probed.
"""

from datetime import date, timedelta

from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.core.errors import AppError
from app.repositories import approval_repo, ticket_repo, trip_repo
from app.schemas import (
    ApprovalStatus,
    CurrentUser,
    ErrorCode,
    Role,
    TicketSummaryOut,
    TripApprovalOut,
    TripCreate,
    TripDetailOut,
    TripListItemOut,
    TripOut,
    TripState,
    TripUpdate,
    today,
)

_NOT_FOUND_MESSAGE = "Trip not found."


# ----------------------------------------------------------------------------- shared helpers
def auto_complete_days() -> int:
    """POLICY_TRIP_AUTO_COMPLETE_DAYS_AFTER_START (default 90) [POL-4.3]."""
    return get_settings().policy_trip_auto_complete_days_after_start


def auto_complete_on(start_date: date) -> date:
    """The day an Active trip is completed by the system: start date + 90 days."""
    return start_date + timedelta(days=auto_complete_days())


def status_label(approval_status: str, trip_state: str | None) -> str:
    """UI label from the spec's Trip lifecycle table."""
    if approval_status == ApprovalStatus.APPROVED:
        return "Approved - Completed" if trip_state == TripState.COMPLETED else "Approved - Active"
    if approval_status == ApprovalStatus.REJECTED:
        return "Rejected"
    return "In Progress"


def is_owner(user: CurrentUser, trip: dict) -> bool:
    return user.employee_id == trip["employee_id"]


def is_approving_manager(user: CurrentUser, trip: dict) -> bool:
    """The trip owner's line manager (permission matrix: 'Direct reports only')."""
    return user.role == Role.MANAGER and trip["owner_manager_id"] == user.employee_id


def visible_trip(db: Connection, user: CurrentUser, trip_id: int, *, for_update: bool = False) -> dict:
    """Load a trip the caller may see (owner or approving manager); otherwise 404."""
    trip = trip_repo.get(db, trip_id, for_update=for_update)
    if trip is None or not (is_owner(user, trip) or is_approving_manager(user, trip)):
        raise AppError(ErrorCode.NOT_FOUND, 404, _NOT_FOUND_MESSAGE)
    return trip


def _trip_out(trip: dict, user: CurrentUser) -> dict:
    """TripOut fields, including the can_* hints computed for the caller."""
    current_day = today()
    owner = is_owner(user, trip)
    approver = is_approving_manager(user, trip)
    status = trip["approval_status"]
    state = trip["trip_state"]
    completes_on = auto_complete_on(trip["start_date"])
    return {
        **trip,
        "status_label": status_label(status, state),
        "earliest_expense_date": trip["created_on"],          # [POL-8.2]
        "auto_complete_on": completes_on,                     # [POL-4.3]
        "can_edit": owner and status == ApprovalStatus.IN_PROGRESS,
        "can_raise_ticket": owner
        and status == ApprovalStatus.APPROVED
        and state == TripState.ACTIVE
        and current_day < completes_on,
        "can_decide": approver
        and status == ApprovalStatus.IN_PROGRESS
        and current_day < completes_on,
        "can_complete": approver and state == TripState.ACTIVE and current_day >= trip["end_date"],
    }


def to_trip_out(trip: dict, user: CurrentUser) -> TripOut:
    """Public builder used by approval_service after a decision."""
    return TripOut(**_trip_out(trip, user))


def _list_item(row: dict) -> TripListItemOut:
    return TripListItemOut(
        **row,
        status_label=status_label(row["approval_status"], row["trip_state"]),
        auto_complete_on=auto_complete_on(row["start_date"]),
    )


# ----------------------------------------------------------------------------- US-05 create
def create_trip(db: Connection, employee: CurrentUser, request: TripCreate) -> TripOut:
    """Create an In Progress trip owned by the authenticated employee."""
    trip = trip_repo.create(db, employee.employee_id, request)
    result = TripOut(**_trip_out(trip, employee))
    db.commit()
    return result


# ----------------------------------------------------------------------------- US-06 list / detail
def list_my_trips(db: Connection, employee: CurrentUser, when: str) -> list[TripListItemOut]:
    """My Trips with Upcoming / Past / All filter (team decision: based on the end date)."""
    rows = trip_repo.list_for_employee(db, employee.employee_id, when, today())
    return [_list_item(row) for row in rows]


def get_trip_detail(db: Connection, user: CurrentUser, trip_id: int) -> TripDetailOut:
    """Trip + decision history + its tickets, for the owner or the approving manager."""
    trip = visible_trip(db, user, trip_id)
    approvals = [TripApprovalOut(**row) for row in approval_repo.list_trip_approvals(db, trip_id)]
    tickets = [TicketSummaryOut(**row) for row in ticket_repo.list_for_trip(db, trip_id)]
    return TripDetailOut(**_trip_out(trip, user), approvals=approvals, tickets=tickets)


# ----------------------------------------------------------------------------- US-07 edit
def update_trip(db: Connection, employee: CurrentUser, trip_id: int, request: TripUpdate) -> TripOut:
    """Owner edits a trip only while In Progress (else 409 TRIP_NOT_EDITABLE) [POL-3.5].
    The same date rules apply: TripUpdate runs the TripBase validators."""
    trip = trip_repo.get(db, trip_id, for_update=True)
    if trip is None or not is_owner(employee, trip):
        raise AppError(ErrorCode.NOT_FOUND, 404, _NOT_FOUND_MESSAGE)
    if trip["approval_status"] != ApprovalStatus.IN_PROGRESS:
        raise AppError(
            ErrorCode.TRIP_NOT_EDITABLE,
            409,
            "This trip can no longer be edited because the manager has already decided it.",
        )
    trip_repo.update_details(db, trip_id, request)
    result = TripOut(**_trip_out(trip_repo.get(db, trip_id), employee))
    db.commit()
    return result


# ----------------------------------------------------------------------------- US-08 / US-09 manager lists
def list_pending_trips(db: Connection, manager: CurrentUser) -> list[TripListItemOut]:
    """Approvals > Trip requests: In Progress trips of direct reports."""
    return [_list_item(row) for row in trip_repo.list_pending_for_manager(db, manager.employee_id)]


def list_trips_to_complete(db: Connection, manager: CurrentUser) -> list[TripListItemOut]:
    """Approvals > Trips to complete: Active trips of direct reports with the end date reached."""
    rows = trip_repo.list_to_complete_for_manager(db, manager.employee_id, today())
    return [_list_item(row) for row in rows]


# ----------------------------------------------------------------------------- US-09 completion
def complete_trip(db: Connection, manager: CurrentUser, trip_id: int) -> TripOut:
    """Approving manager completes an Active trip on/after its end date [POL-4.3].
    Errors: 404 not a direct report's trip; 409 TRIP_NOT_ACTIVE; 409 TRIP_NOT_FINISHED."""
    trip = trip_repo.get(db, trip_id, for_update=True)
    if trip is None:
        raise AppError(ErrorCode.NOT_FOUND, 404, _NOT_FOUND_MESSAGE)
    if is_owner(manager, trip):
        raise AppError(ErrorCode.SELF_APPROVAL, 403, "You cannot complete your own trip.")
    if not is_approving_manager(manager, trip):
        raise AppError(ErrorCode.NOT_FOUND, 404, _NOT_FOUND_MESSAGE)
    if trip["approval_status"] != ApprovalStatus.APPROVED or trip["trip_state"] != TripState.ACTIVE:
        raise AppError(ErrorCode.TRIP_NOT_ACTIVE, 409, "Only an Approved - Active trip can be completed.")
    if today() < trip["end_date"]:
        raise AppError(
            ErrorCode.TRIP_NOT_FINISHED,
            409,
            f"This trip can be completed on or after its end date ({trip['end_date'].isoformat()}).",
        )
    trip_repo.complete_by_manager(db, trip_id, manager.employee_id)
    result = TripOut(**_trip_out(trip_repo.get(db, trip_id), manager))
    db.commit()
    return result


def auto_complete_trips(db: Connection) -> int:
    """System completion (AUTO) of every Active trip at start date + 90 days. Caller commits."""
    return trip_repo.auto_complete_due(db, today(), auto_complete_days())

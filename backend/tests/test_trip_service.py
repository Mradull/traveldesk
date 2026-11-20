"""
Edit only In Progress; approve/reject with comment; approval window; manager-only completion; auto-complete.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0 > Testing strategy
"""

from datetime import timedelta

import pytest
from sqlalchemy import text

from app.core.database import get_engine
from app.core.security import create_access_token
from app.schemas import Role, today


def _authorization_header(employee_id: int, role: Role) -> dict[str, str]:
    token, _ = create_access_token(employee_id, role)
    return {"Authorization": f"Bearer {token}"}


def test_employee_can_submit_trip(api_client, create_test_employee) -> None:
    employee = create_test_employee()
    start_date = today() + timedelta(days=7)
    response = api_client.post(
        "/api/v1/trips",
        headers=_authorization_header(employee["employee_id"], Role.EMPLOYEE),
        json={
            "destination": "Hyderabad",
            "start_date": start_date.isoformat(),
            "end_date": (start_date + timedelta(days=2)).isoformat(),
            "purpose": "Client workshop for annual planning",
        },
    )

    assert response.status_code == 201
    trip = response.json()
    assert trip["trip_id"] > 0
    assert trip["trip_code"].startswith("TRP-")
    assert trip["employee_id"] == employee["employee_id"]
    assert trip["employee_name"] == employee["full_name"]
    assert trip["approval_status"] == "IN_PROGRESS"
    assert trip["trip_state"] is None
    assert trip["status_label"] == "In Progress"
    assert trip["can_edit"] is True
    assert trip["can_raise_ticket"] is False
    assert trip["earliest_expense_date"] == trip["created_on"]
    assert trip["auto_complete_on"] == (
        start_date + timedelta(days=90)
    ).isoformat()

    with get_engine(use_test_database=True).connect() as db:
        saved = db.execute(
            text(
                """
                SELECT employee_id, destination, approval_status, trip_state
                FROM travel_requests
                WHERE trip_id = :trip_id
                """
            ),
            {"trip_id": trip["trip_id"]},
        ).mappings().one()
    assert saved["employee_id"] == employee["employee_id"]
    assert saved["destination"] == "Hyderabad"
    assert saved["approval_status"] == "IN_PROGRESS"
    assert saved["trip_state"] is None


def test_manager_cannot_submit_trip(api_client, create_test_employee) -> None:
    manager = create_test_employee(
        email="vikram.iyer@veridian.example",
        full_name="Vikram Iyer",
        role="MANAGER",
    )
    start_date = today() + timedelta(days=7)

    response = api_client.post(
        "/api/v1/trips",
        headers=_authorization_header(manager["employee_id"], Role.MANAGER),
        json={
            "destination": "Hyderabad",
            "start_date": start_date.isoformat(),
            "end_date": (start_date + timedelta(days=2)).isoformat(),
            "purpose": "Client workshop for annual planning",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_invalid_trip_dates_return_validation_error(
    api_client, create_test_employee
) -> None:
    employee = create_test_employee()
    start_date = today() + timedelta(days=7)

    response = api_client.post(
        "/api/v1/trips",
        headers=_authorization_header(employee["employee_id"], Role.EMPLOYEE),
        json={
            "destination": "Hyderabad",
            "start_date": start_date.isoformat(),
            "end_date": start_date.isoformat(),
            "purpose": "Client workshop for annual planning",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    # Spec US-05: the error appears under the date field, without Pydantic's "Value error, " prefix.
    assert response.json()["error"]["details"] == [
        {"field": "end_date", "msg": "end_date must be later than start_date"}
    ]


@pytest.mark.parametrize(
    "start_offset,end_offset,expected_field",
    [
        (-1, 1, "start_date"),     # start in the past
        (7, 37, "end_date"),       # 31 days (start and end both count) > 30
        (366, 368, "start_date"),  # start more than 365 days ahead
    ],
)
def test_trip_date_limits_return_validation_error(
    api_client,
    create_test_employee,
    start_offset: int,
    end_offset: int,
    expected_field: str,
) -> None:
    employee = create_test_employee()
    start_date = today() + timedelta(days=start_offset)

    response = api_client.post(
        "/api/v1/trips",
        headers=_authorization_header(employee["employee_id"], Role.EMPLOYEE),
        json={
            "destination": "Hyderabad",
            "start_date": start_date.isoformat(),
            "end_date": (today() + timedelta(days=end_offset)).isoformat(),
            "purpose": "Client workshop for annual planning",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    details = response.json()["error"]["details"]
    assert [detail["field"] for detail in details] == [expected_field]
    assert not details[0]["msg"].startswith("Value error")


def test_employee_id_cannot_be_chosen_in_request_body(
    api_client, create_test_employee
) -> None:
    employee = create_test_employee()
    start_date = today() + timedelta(days=7)

    response = api_client.post(
        "/api/v1/trips",
        headers=_authorization_header(employee["employee_id"], Role.EMPLOYEE),
        json={
            "employee_id": employee["employee_id"] + 1,
            "destination": "Hyderabad",
            "start_date": start_date.isoformat(),
            "end_date": (start_date + timedelta(days=2)).isoformat(),
            "purpose": "Client workshop for annual planning",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# =============================================================================
# US-06: My Trips list (team decision: upcoming = ends today or later, past = ended before today)
# =============================================================================
def test_my_trips_lists_only_my_trips_with_filters(api_client, team, make_trip, auth_header) -> None:
    rohan, sara = team["employee"], team["colleague"]
    upcoming = make_trip(rohan["employee_id"], state="ACTIVE", start_offset=3, end_offset=6)
    in_progress = make_trip(rohan["employee_id"], state="IN_PROGRESS", start_offset=20, end_offset=22)
    past = make_trip(rohan["employee_id"], state="ACTIVE", start_offset=-20, end_offset=-17, created_offset=-30)
    make_trip(sara["employee_id"])                                   # must never appear for Rohan

    def ids(when: str | None) -> list[int]:
        url = "/api/v1/trips" + (f"?when={when}" if when else "")
        response = api_client.get(url, headers=auth_header(rohan))
        assert response.status_code == 200
        return [trip["trip_id"] for trip in response.json()]

    assert sorted(ids(None)) == sorted([upcoming, in_progress, past])          # default = all
    assert ids("upcoming") == [upcoming, in_progress]                          # soonest start first
    assert ids("past") == [past]

    card = api_client.get("/api/v1/trips", headers=auth_header(rohan)).json()[0]
    assert {"trip_code", "status_label", "auto_complete_on", "ticket_count", "total_claimed"} <= card.keys()
    assert card["ticket_count"] == 0 and card["total_claimed"] == 0


def test_my_trips_rejects_unknown_filter_and_managers(api_client, team, auth_header) -> None:
    assert api_client.get("/api/v1/trips?when=soon", headers=auth_header(team["employee"])).status_code == 422
    response = api_client.get("/api/v1/trips", headers=auth_header(team["manager"]))
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"


def test_trip_detail_visible_to_owner_and_approving_manager_only(api_client, team, make_trip, auth_header) -> None:
    trip_id = make_trip(team["employee"]["employee_id"], state="IN_PROGRESS")
    url = f"/api/v1/trips/{trip_id}"

    owner_view = api_client.get(url, headers=auth_header(team["employee"]))
    assert owner_view.status_code == 200
    assert owner_view.json()["can_edit"] is True and owner_view.json()["can_decide"] is False

    manager_view = api_client.get(url, headers=auth_header(team["manager"]))
    assert manager_view.status_code == 200 and manager_view.json()["can_decide"] is True

    # Someone else's trip is 404 (not 403), so trip ids cannot be probed.
    for stranger in ("colleague", "other_manager", "outsider"):
        response = api_client.get(url, headers=auth_header(team[stranger]))
        assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"


# =============================================================================
# US-07: edit only while In Progress
# =============================================================================
def _trip_body(destination: str = "Pune", start: int = 10, end: int = 12) -> dict:
    return {
        "destination": destination,
        "start_date": (today() + timedelta(days=start)).isoformat(),
        "end_date": (today() + timedelta(days=end)).isoformat(),
        "purpose": "Updated client workshop agenda",
    }


def test_owner_edits_in_progress_trip(api_client, team, make_trip, auth_header) -> None:
    trip_id = make_trip(team["employee"]["employee_id"], state="IN_PROGRESS")
    response = api_client.put(f"/api/v1/trips/{trip_id}", headers=auth_header(team["employee"]), json=_trip_body())
    assert response.status_code == 200
    assert response.json()["destination"] == "Pune" and response.json()["approval_status"] == "IN_PROGRESS"


@pytest.mark.parametrize("state", ["ACTIVE", "REJECTED", "COMPLETED"])
def test_edit_after_decision_is_409(api_client, team, make_trip, auth_header, state: str) -> None:
    trip_id = make_trip(team["employee"]["employee_id"], state=state)
    response = api_client.put(f"/api/v1/trips/{trip_id}", headers=auth_header(team["employee"]), json=_trip_body())
    assert response.status_code == 409 and response.json()["error"]["code"] == "TRIP_NOT_EDITABLE"


def test_edit_uses_same_date_rules_and_owner_only(api_client, team, make_trip, auth_header) -> None:
    trip_id = make_trip(team["employee"]["employee_id"], state="IN_PROGRESS")
    bad = api_client.put(
        f"/api/v1/trips/{trip_id}", headers=auth_header(team["employee"]), json=_trip_body(start=5, end=5)
    )
    assert bad.status_code == 422 and bad.json()["error"]["details"][0]["field"] == "end_date"
    other = api_client.put(f"/api/v1/trips/{trip_id}", headers=auth_header(team["colleague"]), json=_trip_body())
    assert other.status_code == 404


# =============================================================================
# US-08: manager approves / rejects trip requests
# =============================================================================
def test_manager_approves_trip_from_pending_queue(api_client, team, make_trip, auth_header) -> None:
    trip_id = make_trip(team["employee"]["employee_id"], state="IN_PROGRESS")
    make_trip(team["outsider"]["employee_id"], state="IN_PROGRESS")             # another manager's report

    queue = api_client.get("/api/v1/trips/pending", headers=auth_header(team["manager"])).json()
    assert [trip["trip_id"] for trip in queue] == [trip_id]

    response = api_client.post(
        f"/api/v1/trips/{trip_id}/decision", headers=auth_header(team["manager"]), json={"decision": "APPROVED"}
    )
    assert response.status_code == 200
    assert response.json()["approval_status"] == "APPROVED" and response.json()["trip_state"] == "ACTIVE"
    assert response.json()["status_label"] == "Approved - Active"

    detail = api_client.get(f"/api/v1/trips/{trip_id}", headers=auth_header(team["employee"])).json()
    assert [(a["decision"], a["reviewer_name"]) for a in detail["approvals"]] == [("APPROVED", "Vikram Iyer")]
    assert detail["can_raise_ticket"] is True


def test_reject_needs_comment_and_is_stored(api_client, team, make_trip, auth_header) -> None:
    trip_id = make_trip(team["employee"]["employee_id"], state="IN_PROGRESS")
    url = f"/api/v1/trips/{trip_id}/decision"
    headers = auth_header(team["manager"])

    no_comment = api_client.post(url, headers=headers, json={"decision": "REJECTED"})
    assert no_comment.status_code == 422
    assert no_comment.json()["error"]["details"][0]["field"] == "review_comment"

    rejected = api_client.post(
        url, headers=headers, json={"decision": "REJECTED", "review_comment": "Budget is frozen this quarter."}
    )
    assert rejected.status_code == 200 and rejected.json()["status_label"] == "Rejected"
    with get_engine(use_test_database=True).connect() as db:
        stored = db.execute(text("SELECT review_comment FROM trip_approvals WHERE trip_id = :t"), {"t": trip_id})
        assert stored.scalar_one() == "Budget is frozen this quarter."

    second = api_client.post(url, headers=headers, json={"decision": "APPROVED"})
    assert second.status_code == 409 and second.json()["error"]["code"] == "ALREADY_DECIDED"


def test_decision_permissions(api_client, team, make_trip, auth_header) -> None:
    trip_id = make_trip(team["employee"]["employee_id"], state="IN_PROGRESS")
    url = f"/api/v1/trips/{trip_id}/decision"
    body = {"decision": "APPROVED"}
    assert api_client.post(url, headers=auth_header(team["employee"]), json=body).status_code == 403
    assert api_client.post(url, headers=auth_header(team["other_manager"]), json=body).status_code == 404


def test_approval_window_closes_at_start_plus_90_days(api_client, team, make_trip, auth_header) -> None:
    trip_id = make_trip(
        team["employee"]["employee_id"], state="IN_PROGRESS", start_offset=-90, end_offset=-88, created_offset=-100
    )
    response = api_client.post(
        f"/api/v1/trips/{trip_id}/decision", headers=auth_header(team["manager"]), json={"decision": "APPROVED"}
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "TRIP_APPROVAL_WINDOW_PASSED"


# =============================================================================
# US-09: manager completion and automatic completion
# =============================================================================
def test_manager_completes_finished_trip(api_client, team, make_trip, auth_header) -> None:
    trip_id = make_trip(team["employee"]["employee_id"], start_offset=-20, end_offset=-17, created_offset=-30)
    queue = api_client.get("/api/v1/trips/to-complete", headers=auth_header(team["manager"])).json()
    assert [trip["trip_id"] for trip in queue] == [trip_id]

    response = api_client.post(f"/api/v1/trips/{trip_id}/complete", headers=auth_header(team["manager"]))
    assert response.status_code == 200
    body = response.json()
    assert (body["trip_state"], body["completion_type"], body["completed_by_name"]) == (
        "COMPLETED", "MANAGER", "Vikram Iyer"
    )
    assert body["status_label"] == "Approved - Completed"


def test_completion_rules(api_client, team, make_trip, auth_header) -> None:
    future = make_trip(team["employee"]["employee_id"], start_offset=3, end_offset=6)
    not_finished = api_client.post(f"/api/v1/trips/{future}/complete", headers=auth_header(team["manager"]))
    assert not_finished.status_code == 409 and not_finished.json()["error"]["code"] == "TRIP_NOT_FINISHED"

    employee_try = api_client.post(f"/api/v1/trips/{future}/complete", headers=auth_header(team["employee"]))
    assert employee_try.status_code == 403                                     # employees have no complete

    in_progress = make_trip(team["employee"]["employee_id"], state="IN_PROGRESS", start_offset=-3, end_offset=-1)
    not_active = api_client.post(f"/api/v1/trips/{in_progress}/complete", headers=auth_header(team["manager"]))
    assert not_active.status_code == 409 and not_active.json()["error"]["code"] == "TRIP_NOT_ACTIVE"


def test_auto_complete_job_at_start_plus_90_days(team, make_trip, test_engine) -> None:
    from app.services import jobs

    due = make_trip(team["employee"]["employee_id"], start_offset=-90, end_offset=-88, created_offset=-95)
    not_yet = make_trip(team["employee"]["employee_id"], start_offset=-89, end_offset=-87, created_offset=-95)
    with test_engine.begin() as db:
        assert jobs.auto_complete_trips(db) == 1
    with test_engine.connect() as db:
        rows = dict(
            db.execute(
                text("SELECT trip_id, completion_type FROM travel_requests WHERE trip_id IN (:a, :b)"),
                {"a": due, "b": not_yet},
            ).all()
        )
    assert rows == {due: "AUTO", not_yet: None}

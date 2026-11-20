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

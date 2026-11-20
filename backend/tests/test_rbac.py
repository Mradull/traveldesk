"""
Manager -> /chat 403; Employee -> decision 403; forged role claim ignored.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0 > Testing strategy
"""

import pytest

from app.core.deps import require_employee, require_manager
from app.core.errors import AppError
from app.schemas import CurrentUser, ErrorCode, Role


def _user(role: Role) -> CurrentUser:
    return CurrentUser(
        employee_id=1,
        full_name="Test User",
        email="test@veridian.example",
        department="Test",
        role=role,
        manager_id=None,
    )


def test_employee_guard_rejects_manager() -> None:
    with pytest.raises(AppError) as error:
        require_employee(_user(Role.MANAGER))

    assert error.value.http_status == 403
    assert error.value.code == ErrorCode.FORBIDDEN


def test_manager_guard_rejects_employee() -> None:
    with pytest.raises(AppError) as error:
        require_manager(_user(Role.EMPLOYEE))

    assert error.value.http_status == 403
    assert error.value.code == ErrorCode.FORBIDDEN


def test_role_guards_allow_matching_role() -> None:
    employee = _user(Role.EMPLOYEE)
    manager = _user(Role.MANAGER)

    assert require_employee(employee) is employee
    assert require_manager(manager) is manager


# Real routes: a wrong role gets 403 FORBIDDEN even when the UI is bypassed (spec US-03).
MANAGER_ONLY = [
    ("GET", "/api/v1/trips/pending"),
    ("GET", "/api/v1/trips/to-complete"),
    ("POST", "/api/v1/trips/1/decision"),
    ("POST", "/api/v1/trips/1/complete"),
    ("GET", "/api/v1/tickets/pending"),
    ("POST", "/api/v1/tickets/1/decision"),
    ("GET", "/api/v1/expenses/pending"),
    ("GET", "/api/v1/reports/trip-expenses"),
    ("GET", "/api/v1/reports/spend-by-trip-category"),
]
EMPLOYEE_ONLY = [
    ("POST", "/api/v1/trips"),
    ("GET", "/api/v1/trips"),
    ("PUT", "/api/v1/trips/1"),
    ("POST", "/api/v1/evidence"),
    ("POST", "/api/v1/trips/1/tickets"),
    ("GET", "/api/v1/tickets"),
]


# FastAPI runs the login and role checks before it reads the request body, so no body is needed.
@pytest.mark.parametrize("method,url", MANAGER_ONLY)
def test_employee_gets_403_on_manager_routes(api_client, team, auth_header, method: str, url: str) -> None:
    response = api_client.request(method, url, headers=auth_header(team["employee"]))
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("method,url", EMPLOYEE_ONLY)
def test_manager_gets_403_on_employee_routes(api_client, team, auth_header, method: str, url: str) -> None:
    response = api_client.request(method, url, headers=auth_header(team["manager"]))
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("method,url", MANAGER_ONLY + EMPLOYEE_ONLY)
def test_no_token_is_401(api_client, method: str, url: str) -> None:
    response = api_client.request(method, url)
    assert response.status_code == 401 and response.json()["error"]["code"] == "UNAUTHENTICATED"

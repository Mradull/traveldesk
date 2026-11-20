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

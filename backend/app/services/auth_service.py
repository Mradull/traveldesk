"""
Login: find employee by email, verify bcrypt hash, issue JWT. Same INVALID_CREDENTIALS for wrong email or password.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from sqlalchemy.engine import Connection

from app.core.errors import AppError
from app.core.security import create_access_token, verify_password
from app.repositories import employee_repo
from app.schemas import CurrentUser, EmployeeOut, ErrorCode, LoginRequest, Role, TokenOut

INVALID_CREDENTIALS_MESSAGE = "Email or password is incorrect."


def login(db: Connection, request: LoginRequest) -> TokenOut:
    employee = employee_repo.get_for_authentication(db, request.email)
    if (
        employee is None
        or not employee["is_active"]
        or not verify_password(request.password, employee["password_hash"])
    ):
        raise AppError(
            ErrorCode.INVALID_CREDENTIALS,
            401,
            INVALID_CREDENTIALS_MESSAGE,
        )

    token, expires_in = create_access_token(
        employee["employee_id"],
        Role(employee["role"]),
    )
    user = EmployeeOut.model_validate(employee)
    return TokenOut(access_token=token, expires_in=expires_in, user=user)


def get_current_employee(db: Connection, employee_id: int) -> CurrentUser:
    employee = employee_repo.get_public_by_id(db, employee_id)
    if employee is None:
        raise AppError(
            ErrorCode.INVALID_TOKEN,
            401,
            "The access token is invalid.",
        )
    return CurrentUser.model_validate(employee)

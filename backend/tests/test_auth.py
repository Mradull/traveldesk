"""
Login OK / wrong (same 401); expired and tampered tokens; role read from the DB.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0 > Testing strategy
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import get_engine
from app.core.security import create_access_token, hash_password, verify_password
from app.schemas import Role


def _test_jwt_secret() -> str:
    secret = get_settings().jwt_secret_key
    assert secret is not None
    return secret.get_secret_value()


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    password = "DemoPassword123!"
    password_hash = hash_password(password)

    assert password_hash != password
    assert verify_password(password, password_hash)
    assert not verify_password("WrongPassword123!", password_hash)


def test_login_returns_contract_token(api_client, create_test_employee) -> None:
    create_test_employee()
    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": "ROHAN.MEHTA@VERIDIAN.EXAMPLE", "password": "DemoPassword123!"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert body["user"]["role"] == "EMPLOYEE"
    assert "password_hash" not in body["user"]

    payload = jwt.decode(
        body["access_token"],
        _test_jwt_secret(),
        algorithms=[get_settings().jwt_algorithm],
    )
    assert set(payload) == {"sub", "role", "iat", "exp"}
    assert payload["sub"] == str(body["user"]["employee_id"])


@pytest.mark.parametrize(
    "email,password",
    [
        ("unknown@veridian.example", "DemoPassword123!"),
        ("rohan.mehta@veridian.example", "WrongPassword123!"),
    ],
)
def test_wrong_email_and_password_have_same_error(
    api_client, create_test_employee, email: str, password: str
) -> None:
    create_test_employee()
    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert response.json()["error"]["message"] == "Email or password is incorrect."


def test_me_uses_current_database_role(api_client, create_test_employee) -> None:
    employee = create_test_employee()
    token, _ = create_access_token(employee["employee_id"], Role.EMPLOYEE)
    with get_engine(use_test_database=True).begin() as db:
        db.execute(
            text("UPDATE employees SET role = 'MANAGER' WHERE employee_id = :employee_id"),
            {"employee_id": employee["employee_id"]},
        )

    response = api_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "MANAGER"
    assert "password_hash" not in response.json()


def test_me_ignores_forged_role_claim(api_client, create_test_employee) -> None:
    employee = create_test_employee()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(employee["employee_id"]),
            "role": "MANAGER",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=10)).timestamp()),
        },
        _test_jwt_secret(),
        algorithm=get_settings().jwt_algorithm,
    )

    response = api_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "EMPLOYEE"


def test_missing_bearer_token_has_error_envelope(api_client) -> None:
    response = api_client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert response.headers.get("X-Request-ID")
    assert response.headers.get("X-Correlation-ID")


def test_expired_token_has_token_expired_code(
    api_client, create_test_employee
) -> None:
    employee = create_test_employee()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(employee["employee_id"]),
            "role": "EMPLOYEE",
            "iat": int((now - timedelta(minutes=2)).timestamp()),
            "exp": int((now - timedelta(minutes=1)).timestamp()),
        },
        _test_jwt_secret(),
        algorithm=get_settings().jwt_algorithm,
    )

    response = api_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_tampered_token_has_invalid_token_code(
    api_client, create_test_employee
) -> None:
    employee = create_test_employee()
    token, _ = create_access_token(employee["employee_id"], Role.EMPLOYEE)
    tampered_token = token[:-1] + ("a" if token[-1] != "a" else "b")

    response = api_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"

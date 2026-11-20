"""
Test DB from migrations on TEST_DATABASE_URL, truncation, frozen schemas.today(), token helper (Joyal);
fake chat model, respx router (Piyush).

Owner: Joyal (M1) + Piyush (M2), see 'Shared files'  |  Spec: Agile Spec v2.0 > Testing strategy
"""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app.core.config import get_settings
from app.core.database import connection, get_engine
from app.core.deps import get_db
from app.core.security import hash_password
from app.main import app


# --- Joyal/M1 test fixtures ---
@pytest.fixture(autouse=True)
def test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "test-only-traveldesk-jwt-secret-key-long-enough-for-hs256",
    )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def test_engine() -> Engine:
    return get_engine(use_test_database=True)


@pytest.fixture
def clean_test_database(test_engine: Engine) -> Iterator[None]:
    with test_engine.begin() as db:
        db.execute(text("TRUNCATE employees RESTART IDENTITY CASCADE"))
    yield
    with test_engine.begin() as db:
        db.execute(text("TRUNCATE employees RESTART IDENTITY CASCADE"))


@pytest.fixture
def api_client() -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Connection]:
        with connection(use_test_database=True) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def create_test_employee(
    test_engine: Engine,
    clean_test_database: None,
) -> Callable[..., dict]:
    def create(
        *,
        full_name: str = "Rohan Mehta",
        email: str = "rohan.mehta@veridian.example",
        password: str = "DemoPassword123!",
        department: str = "Tax",
        role: str = "EMPLOYEE",
        manager_id: int | None = None,
    ) -> dict:
        with test_engine.begin() as db:
            row = db.execute(
                text(
                    """
                    INSERT INTO employees
                        (full_name, email, password_hash, department, role, manager_id)
                    VALUES
                        (:full_name, :email, :password_hash, :department, :role, :manager_id)
                    RETURNING employee_id, full_name, email, department, role, manager_id
                    """
                ),
                {
                    "full_name": full_name,
                    "email": email.lower(),
                    "password_hash": hash_password(password),
                    "department": department,
                    "role": role,
                    "manager_id": manager_id,
                },
            ).mappings().one()
        return dict(row)

    return create

"""
Test DB from migrations on TEST_DATABASE_URL, truncation, frozen schemas.today(), token helper (Joyal);
fake chat model, respx router (Piyush).

Owner: Joyal (M1) + Piyush (M2), see 'Shared files'  |  Spec: Agile Spec v2.0 > Testing strategy
"""

import hashlib
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app.core.config import get_settings
from app.core.database import connection, get_engine
from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.schemas import Role


# --- Joyal/M1 test fixtures ---
@pytest.fixture(scope="session", autouse=True)
def test_database_schema() -> None:
    """Spec > Testing strategy: apply the migrations to traveldesk_test before any test runs.
    Safe to repeat: already-applied migrations are skipped (schema_migrations)."""
    from scripts.init_db import run_migrations

    run_migrations(use_test_database=True)


@pytest.fixture
def frozen_today(monkeypatch: pytest.MonkeyPatch):
    """Opt-in: freeze schemas.today() for pure validation tests, e.g. frozen_today(date(2026, 11, 20)).
    Not automatic, because the database's CURRENT_DATE (trip created_on) cannot be frozen."""
    from app import schemas

    def freeze(day):
        monkeypatch.setattr(schemas, "today", lambda: day)
        return day

    return freeze


@pytest.fixture(autouse=True)
def test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "test-only-traveldesk-jwt-secret-key-long-enough-for-hs256",
    )
    # APP_ENV=test makes every default database connection use TEST_DATABASE_URL (core/database.py),
    # and the hourly scheduler never starts during tests.
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def test_engine() -> Engine:
    return get_engine(use_test_database=True)


def _empty_test_database(test_engine: Engine) -> None:
    """Remove every row (all tables link to employees, except error_logs) and restart the
    TRP/TKT/EXP/EVD numbering, so traveldesk_test is never left with confusing leftovers."""
    with test_engine.begin() as db:
        db.execute(text("TRUNCATE employees, error_logs RESTART IDENTITY CASCADE"))
        db.execute(text("SELECT setval('evidence_code_seq', 1, false)"))


@pytest.fixture
def clean_test_database(test_engine: Engine) -> Iterator[None]:
    _empty_test_database(test_engine)
    yield
    _empty_test_database(test_engine)


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


# A tiny byte string that starts with the JPEG signature (enough for the file-type check).
JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"


@pytest.fixture
def auth_header() -> Callable[[dict], dict[str, str]]:
    """auth_header(employee_row) -> {'Authorization': 'Bearer <jwt>'} signed with the test key."""

    def build(employee: dict) -> dict[str, str]:
        token, _ = create_access_token(employee["employee_id"], Role(employee["role"]))
        return {"Authorization": f"Bearer {token}"}

    return build


@pytest.fixture
def team(create_test_employee: Callable[..., dict]) -> dict[str, dict]:
    """Vikram manages Rohan and Sara; Meera is another manager who manages Kiran only."""
    manager = create_test_employee(
        full_name="Vikram Iyer", email="vikram.iyer@veridian.example", department="Advisory", role="MANAGER"
    )
    other_manager = create_test_employee(
        full_name="Meera Nair", email="meera.nair@veridian.example", department="Audit", role="MANAGER"
    )
    return {
        "manager": manager,
        "other_manager": other_manager,
        "employee": create_test_employee(manager_id=manager["employee_id"]),
        "colleague": create_test_employee(
            full_name="Sara Thomas", email="sara.thomas@veridian.example", department="Assurance",
            manager_id=manager["employee_id"],
        ),
        "outsider": create_test_employee(
            full_name="Kiran Das", email="kiran.das@veridian.example", department="Audit",
            manager_id=other_manager["employee_id"],
        ),
    }


@pytest.fixture
def make_trip(test_engine: Engine) -> Callable[..., int]:
    """Insert a trip in any state directly (test set-up only). Offsets are days from today."""

    def make(
        employee_id: int,
        *,
        state: str = "ACTIVE",            # IN_PROGRESS | REJECTED | ACTIVE | COMPLETED
        start_offset: int = 3,
        end_offset: int = 6,
        created_offset: int = -5,
        destination: str = "Bengaluru",
    ) -> int:
        approval_status = {"IN_PROGRESS": "IN_PROGRESS", "REJECTED": "REJECTED"}.get(state, "APPROVED")
        trip_state = state if state in ("ACTIVE", "COMPLETED") else None
        with test_engine.begin() as db:
            return db.execute(
                text(
                    """
                    INSERT INTO travel_requests
                        (employee_id, destination, start_date, end_date, purpose,
                         approval_status, trip_state, completion_type, completed_at, created_on)
                    VALUES
                        (:employee_id, :destination, CURRENT_DATE + :start_offset, CURRENT_DATE + :end_offset,
                         'Client workshop for annual planning', :approval_status, :trip_state,
                         CASE WHEN :trip_state = 'COMPLETED' THEN 'AUTO' END,
                         CASE WHEN :trip_state = 'COMPLETED' THEN now() END,
                         CURRENT_DATE + :created_offset)
                    RETURNING trip_id
                    """
                ),
                {
                    "employee_id": employee_id, "destination": destination,
                    "start_offset": start_offset, "end_offset": end_offset, "created_offset": created_offset,
                    "approval_status": approval_status, "trip_state": trip_state,
                },
            ).scalar_one()

    return make


@pytest.fixture
def make_evidence(test_engine: Engine) -> Callable[..., str]:
    """Insert one uploaded photo for an employee; each call gets different bytes unless given."""
    counter = iter(range(1, 10_000))

    def make(employee_id: int, content: bytes | None = None, hours_ago: int = 0) -> str:
        content = content if content is not None else JPEG_HEADER + f"receipt-{next(counter)}".encode()
        with test_engine.begin() as db:
            evidence_id = db.execute(
                text(
                    """
                    INSERT INTO expense_evidence
                        (employee_id, original_filename, mime_type, size_bytes, sha256, uploaded_at)
                    VALUES (:employee_id, 'receipt.jpg', 'image/jpeg', :size, :sha256,
                            now() - make_interval(hours => :hours_ago))
                    RETURNING evidence_id
                    """
                ),
                {"employee_id": employee_id, "size": len(content),
                 "sha256": hashlib.sha256(content).hexdigest(), "hours_ago": hours_ago},
            ).scalar_one()
            db.execute(
                text("INSERT INTO evidence_files (evidence_id, content) VALUES (:evidence_id, :content)"),
                {"evidence_id": evidence_id, "content": content},
            )
        return str(evidence_id)

    return make


@pytest.fixture
def seeded_test_database(test_engine: Engine, clean_test_database: None) -> None:
    """Load database/seed/seed_data.sql + the 8 photos into the emptied test database."""
    from scripts.init_db import seed_if_empty

    seed_if_empty(test_engine, hash_password("TestOnlySeed123"))

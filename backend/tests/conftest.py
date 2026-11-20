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


# --- Piyush/M2 test fixtures ---
# Opt-in: each Vera test module starts with  pytestmark = pytest.mark.usefixtures("vera_db"),
# so Joyal's tests are not affected. No test calls the real AI provider, Open-Meteo or the
# embedding model: the LLM is a scripted fake, Open-Meteo is mocked with respx, and the
# embedder is a deterministic bag-of-words fake.
import math
import re
from datetime import date, timedelta

import httpx
import respx
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app import schemas
from app.ai import llm_client
from app.chat import guardrails
from app.core.database import transaction
from app.rag import embeddings, retriever
from app.services import weather_service

TODAY = date(2026, 11, 20)        # frozen "today" for every Vera test


@pytest.fixture
def vera_db(monkeypatch: pytest.MonkeyPatch, test_engine: Engine) -> Iterator[None]:
    """Vera tests: start traveldesk_test from empty tables with 1 manager + 2 employees, freeze today,
    fake embedder, no caches. (APP_ENV=test, set by test_jwt_secret, already sends every
    transaction()/connection() to traveldesk_test.)"""
    with test_engine.begin() as db:
        # CASCADE also empties chat_*, the three AI log tables and every business table
        db.execute(text("TRUNCATE employees, policy_chunks, error_logs RESTART IDENTITY CASCADE"))
        db.execute(text("""
            INSERT INTO employees (full_name, email, password_hash, department, role, manager_id) VALUES
            ('Vikram Iyer', 'vikram.iyer@veridian.example', 'x', 'Advisory', 'MANAGER', NULL),
            ('Rohan Mehta', 'rohan.mehta@veridian.example', 'x', 'Tax', 'EMPLOYEE', 1),
            ('Sara Thomas', 'sara.thomas@veridian.example', 'x', 'Assurance', 'EMPLOYEE', 1)"""))
    monkeypatch.setattr(schemas, "today", lambda: TODAY)
    monkeypatch.setattr(embeddings, "_embedder", FakeEmbeddings())
    retriever._cache["fingerprint"] = None
    weather_service.clear_cache()
    guardrails.reset_rate_limits()
    yield
    llm_client.set_chat_model(None)


def _user(employee_id: int) -> schemas.CurrentUser:
    with transaction() as conn:
        row = conn.execute(text("SELECT employee_id, full_name, email, department, role, manager_id "
                                "FROM employees WHERE employee_id = :i"), {"i": employee_id}).mappings().one()
    return schemas.CurrentUser(**row)


@pytest.fixture
def manager(vera_db: None) -> schemas.CurrentUser:
    return _user(1)


@pytest.fixture
def employee(vera_db: None) -> schemas.CurrentUser:
    return _user(2)


@pytest.fixture
def other_employee(vera_db: None) -> schemas.CurrentUser:
    return _user(3)


@pytest.fixture
def auth() -> Callable[[schemas.CurrentUser], dict]:
    """auth(user) -> {'Authorization': 'Bearer <jwt>'} signed with Joyal's create_access_token."""
    return lambda user: {"Authorization": f"Bearer {create_access_token(user.employee_id, user.role)[0]}"}


@pytest.fixture
def client(api_client: TestClient) -> TestClient:
    """Joyal's api_client (get_db -> test database) under the name the Vera tests use."""
    return api_client


class ScriptedChatModel(GenericFakeChatModel):
    """LangChain's fake chat model, extended so it accepts bind_tools() and records each call.
    Script items: AIMessage / str replies, or an Exception instance to raise."""
    calls: list = []           # [(messages, tool names bound)]
    bound: list = []

    def bind_tools(self, tools, **kwargs):
        self.bound = [t.name for t in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append((messages, list(self.bound)))
        self.bound = []
        item = next(self.messages)
        if isinstance(item, Exception):
            raise item
        message = item if isinstance(item, AIMessage) else AIMessage(content=item)
        return ChatResult(generations=[ChatGeneration(message=message)])


@pytest.fixture
def fake_llm() -> Iterator[Callable[..., ScriptedChatModel]]:
    """fake_llm(*replies) installs a scripted model and returns it (inspect .calls afterwards)."""
    def install(*replies):
        model = ScriptedChatModel(messages=iter(replies), calls=[], bound=[])
        llm_client.set_chat_model(model)
        return model
    yield install
    llm_client.set_chat_model(None)


def tool_call(name: str, args: dict, call_id: str = "call-1") -> AIMessage:
    """An AIMessage in which the model asks for one tool."""
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


_STOP = {"the", "a", "an", "is", "are", "what", "how", "do", "i", "my", "to", "of", "for", "in", "on", "and", "or",
         "can", "it", "be", "you", "me", "per", "with", "at", "this", "that", "your", "if", "by", "as", "not"}


class FakeEmbeddings(Embeddings):
    """Deterministic bag-of-words vectors (384 dims, normalised): no model download in tests."""

    def _vec(self, text_: str) -> list[float]:
        v = [0.0] * 384
        for word in re.findall(r"[a-z]+", text_.lower()):
            word = word[:-1] if word.endswith("s") and len(word) > 3 else word
            if word not in _STOP:
                v[int(hashlib.md5(word.encode()).hexdigest(), 16) % len(v)] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text_):
        return self._vec(text_)


@pytest.fixture
def policy_index(vera_db: None) -> None:
    """Ingest the real business document (backend/data/expense_policy.txt) with the fake embedder."""
    from scripts.ingest_policy import main as ingest
    ingest()


GEO_BENGALURU = {"results": [{"name": "Bengaluru", "admin1": "Karnataka", "country": "India", "country_code": "IN",
                              "latitude": 12.97, "longitude": 77.59, "population": 8443675}]}


def forecast_json(start: date, days: int, **overrides) -> dict:
    """Open-Meteo daily JSON for `days` days from `start` with fixed, easy-to-check values."""
    dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    daily = {"time": dates, "weather_code": [61] * days, "temperature_2m_min": [19.4] * days,
             "temperature_2m_max": [27.8] * days, "precipitation_probability_max": [70] * days,
             "precipitation_sum": [4.2] * days, "wind_speed_10m_max": [14.0] * days}
    daily.update(overrides)
    return {"daily": daily}


@pytest.fixture
def weather_api() -> Iterator[respx.MockRouter]:
    """respx router for Open-Meteo. Defaults: geocoding finds Bengaluru; forecast echoes the
    requested dates with the fixed values of forecast_json(). Override routes per test."""
    settings = get_settings()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(settings.weather_geocoding_url, name="geo").mock(return_value=httpx.Response(200, json=GEO_BENGALURU))

        def echo_forecast(request: httpx.Request):
            s = date.fromisoformat(request.url.params["start_date"])
            e = date.fromisoformat(request.url.params["end_date"])
            return httpx.Response(200, json=forecast_json(s, (e - s).days + 1))
        mock.get(settings.weather_forecast_url, name="forecast").mock(side_effect=echo_forecast)
        yield mock


def rows(sql: str, **params) -> list[dict]:
    """Assert on table contents (runs inside vera_db, so it reads traveldesk_test)."""
    with transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings()]

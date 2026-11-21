"""
SQLAlchemy 2 engine (psycopg 3) for the local PostgreSQL, connection helper and transaction() context manager.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from app.core.config import get_settings

_engines: dict[tuple[str, bool], Engine] = {}


def _wants_test_database(use_test_database: bool | None) -> bool:
    """None = decide from APP_ENV: 'test' (set by tests/conftest.py) uses TEST_DATABASE_URL, so code
    that opens its own transaction (scheduler jobs, error logging) never touches the real database
    during pytest. An explicit True/False always wins."""
    if use_test_database is None:
        return get_settings().app_env.strip().lower() == "test"
    return use_test_database


def get_engine(*, use_test_database: bool | None = None) -> Engine:
    """Get a pooled PostgreSQL engine for the app or the isolated pytest database."""
    use_test_database = _wants_test_database(use_test_database)
    settings = get_settings()
    database_url = (
        settings.test_database_url if use_test_database else settings.database_url
    )
    variable_name = "TEST_DATABASE_URL" if use_test_database else "DATABASE_URL"
    if not database_url:
        raise RuntimeError(
            f"{variable_name} is not configured. Set it in backend/.env "
            "before connecting to PostgreSQL."
        )

    cache_key = (database_url, use_test_database)
    if cache_key not in _engines:
        _engines[cache_key] = create_engine(
            database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle_seconds,
            pool_pre_ping=True,
            connect_args={
                "connect_timeout": settings.db_connect_timeout_seconds,
                "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
            },
        )
    return _engines[cache_key]


@contextmanager
def connection(*, use_test_database: bool | None = None) -> Iterator[Connection]:
    """Yield a connection for read operations and close it when the block ends."""
    with get_engine(use_test_database=use_test_database).connect() as db_connection:
        yield db_connection


@contextmanager
def transaction(*, use_test_database: bool | None = None) -> Iterator[Connection]:
    """Run database operations atomically and roll back if the block raises."""
    with get_engine(use_test_database=use_test_database).begin() as db_connection:
        yield db_connection

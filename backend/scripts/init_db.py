"""
Apply populated database/migrations/*.sql in order, recording each successful migration in
schema_migrations. A full initialization refuses to run while any migration is a placeholder.

Use --through 001_core_tables.sql --test-database to apply only the first migration to the
isolated traveldesk_test database while developing.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.database import get_engine

MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"
SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def _contains_sql(sql: str) -> bool:
    """Return false for empty or comment-only migration placeholders."""
    without_block_comments = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    without_line_comments = re.sub(r"(?m)^\s*--.*$", "", without_block_comments)
    return bool(without_line_comments.strip())


def _select_migrations(
    migration_paths: Sequence[Path], through: str | None = None
) -> list[Path]:
    """Validate and select ordered migrations without touching the database."""
    ordered_paths = sorted(migration_paths, key=lambda path: path.name)
    if through is not None:
        target_index = next(
            (index for index, path in enumerate(ordered_paths) if path.name == through),
            None,
        )
        if target_index is None:
            raise ValueError(f"Unknown migration target: {through}")
        ordered_paths = ordered_paths[: target_index + 1]

    placeholders = [
        path.name
        for path in ordered_paths
        if not _contains_sql(path.read_text(encoding="utf-8"))
    ]
    if placeholders:
        names = ", ".join(placeholders)
        raise ValueError(
            f"Cannot apply migrations because these files are empty placeholders: {names}"
        )
    return ordered_paths


def _ensure_migration_table(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(SCHEMA_MIGRATIONS_SQL)


def _apply_migration(engine: Engine, migration_path: Path) -> bool:
    """Apply one migration and its tracking row atomically; return whether it was new."""
    version = migration_path.name
    sql = migration_path.read_text(encoding="utf-8")

    with engine.begin() as connection:
        already_applied = connection.execute(
            text("SELECT 1 FROM schema_migrations WHERE version = :version"),
            {"version": version},
        ).scalar_one_or_none()
        if already_applied is not None:
            return False

        # psycopg's simple-query mode accepts a complete migration script containing
        # multiple statements, including the PL/pgSQL function in migration 001.
        raw_connection = connection.connection.driver_connection
        raw_connection.execute(sql, prepare=False)
        connection.execute(
            text("INSERT INTO schema_migrations (version) VALUES (:version)"),
            {"version": version},
        )
    return True


def run_migrations(
    *,
    through: str | None = None,
    use_test_database: bool = False,
    migration_dir: Path = MIGRATIONS_DIR,
) -> list[str]:
    """Apply completed migrations in order and return newly applied filenames."""
    migration_paths = list(migration_dir.glob("*.sql"))
    if not migration_paths:
        raise ValueError(f"No SQL migrations found in {migration_dir}")

    selected_paths = _select_migrations(migration_paths, through)
    engine = get_engine(use_test_database=use_test_database)
    _ensure_migration_table(engine)

    newly_applied = []
    for migration_path in selected_paths:
        if _apply_migration(engine, migration_path):
            newly_applied.append(migration_path.name)
    return newly_applied


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply TravelDesk PostgreSQL migrations.")
    parser.add_argument(
        "--through",
        metavar="MIGRATION_FILE",
        help="Apply migrations only through this filename (inclusive).",
    )
    parser.add_argument(
        "--test-database",
        action="store_true",
        help="Use TEST_DATABASE_URL instead of DATABASE_URL.",
    )
    args = parser.parse_args()

    try:
        newly_applied = run_migrations(
            through=args.through,
            use_test_database=args.test_database,
        )
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    if newly_applied:
        print("Applied migrations: " + ", ".join(newly_applied))
    else:
        print("No new migrations to apply.")


if __name__ == "__main__":
    main()

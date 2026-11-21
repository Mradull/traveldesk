"""
Apply populated database/migrations/*.sql in order, recording each successful migration in
schema_migrations. A full initialization refuses to run while any migration is a placeholder.
A full run (no --through) then loads the seed data ONCE, only while the employees table is empty:
database/seed/seed_data.sql plus the 8 receipt photos in database/seed/evidence/.

Use --through 001_core_tables.sql --test-database to apply only the first migration to the
isolated traveldesk_test database while developing (no seed is loaded with --through).

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

import argparse
import re
import sys
from hashlib import sha256
from pathlib import Path
from typing import Sequence

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.core.database import get_engine
from app.core.security import hash_password
from app.schemas import MIN_PASSWORD_CHARS

MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"
SEED_SQL_PATH = PROJECT_ROOT / "database" / "seed" / "seed_data.sql"
SEED_EVIDENCE_DIR = PROJECT_ROOT / "database" / "seed" / "evidence"
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


def _seed_password_hash() -> str:
    """bcrypt-hash SEED_DEMO_PASSWORD from .env (the same hash_password() used at login)."""
    secret = get_settings().seed_demo_password
    password = secret.get_secret_value() if secret is not None else ""
    if len(password) < MIN_PASSWORD_CHARS or password.startswith("change-me-"):
        raise RuntimeError(
            f"Set a private SEED_DEMO_PASSWORD of at least {MIN_PASSWORD_CHARS} characters "
            "in backend/.env before loading the seed data."
        )
    return hash_password(password)


def seed_if_empty(engine: Engine, password_hash: str) -> bool:
    """Load seed_data.sql and the 8 seed photos in one transaction; skip if employees exist."""
    with engine.begin() as connection:
        if connection.execute(text("SELECT EXISTS (SELECT 1 FROM employees)")).scalar_one():
            return False

        # The hash is passed as a transaction-local setting, so seed_data.sql never contains it.
        connection.execute(
            text("SELECT set_config('traveldesk.seed_password_hash', :password_hash, true)"),
            {"password_hash": password_hash},
        )
        raw_connection = connection.connection.driver_connection
        raw_connection.execute(SEED_SQL_PATH.read_text(encoding="utf-8"), prepare=False)

        # Load each photo's bytes, after checking the file is exactly the one seed_data.sql describes.
        evidence_rows = connection.execute(
            text(
                "SELECT evidence_id, original_filename, size_bytes, sha256 "
                "FROM expense_evidence ORDER BY evidence_code"
            )
        ).mappings().all()
        for row in evidence_rows:
            content = (SEED_EVIDENCE_DIR / row["original_filename"]).read_bytes()
            if len(content) != row["size_bytes"] or sha256(content).hexdigest() != row["sha256"]:
                raise RuntimeError(
                    f"Seed photo {row['original_filename']} does not match its size/sha256 in seed_data.sql."
                )
            connection.execute(
                text("INSERT INTO evidence_files (evidence_id, content) VALUES (:evidence_id, :content)"),
                {"evidence_id": row["evidence_id"], "content": content},
            )
    return True


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

    load_seed = args.through is None
    try:
        # Check the seed password BEFORE touching the database, so a bad .env changes nothing.
        password_hash = _seed_password_hash() if load_seed else None
        newly_applied = run_migrations(
            through=args.through,
            use_test_database=args.test_database,
        )
        seeded = (
            seed_if_empty(get_engine(use_test_database=args.test_database), password_hash)
            if load_seed
            else False
        )
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    if newly_applied:
        print("Applied migrations: " + ", ".join(newly_applied))
    else:
        print("No new migrations to apply.")
    if load_seed:
        print("Seed data loaded." if seeded else "Seed skipped: employees already exist.")


if __name__ == "__main__":
    main()

"""
GET /health: database check (Joyal); weather API, AI provider, policy index and scheduler checks (Piyush).

Owner: Joyal (M1) + Piyush (M2), see 'Shared files'  |  Spec: Agile Spec v2.0
"""

import time
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import connection
from app.schemas import DependencyHealth, HealthOut

router = APIRouter(tags=["health"])


# --- Joyal/M1: database check ---
def check_database() -> DependencyHealth:
    """SELECT 1 on PostgreSQL. Never raises: a down database is reported, not thrown."""
    started = time.perf_counter()
    try:
        with connection() as db:
            db.execute(text("SELECT 1"))
        return DependencyHealth(name="database", ok=True, latency_ms=round((time.perf_counter() - started) * 1000))
    except Exception as exc:  # noqa: BLE001 - health must answer even when the DB is down
        return DependencyHealth(name="database", ok=False, detail=type(exc).__name__)


# --- Piyush/M2: add check_weather_api, check_ai_provider, check_policy_index, check_scheduler here
#     (each its own function returning DependencyHealth) and append them to CHECKS ---
CHECKS: list[Callable[[], DependencyHealth]] = [
    check_database,
]


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    """Public. down = database not reachable; degraded = database ok but another check failed; ok."""
    dependencies = [check() for check in CHECKS]
    database_ok = next((dep.ok for dep in dependencies if dep.name == "database"), False)
    if not database_ok:
        status = "down"
    elif all(dep.ok for dep in dependencies):
        status = "ok"
    else:
        status = "degraded"
    return HealthOut(status=status, dependencies=dependencies, checked_at=datetime.now(timezone.utc))

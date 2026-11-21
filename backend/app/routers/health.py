"""
GET /health: database check (Joyal); weather API, AI provider, policy index and scheduler checks (Piyush).

Owner: Joyal (M1) + Piyush (M2), see 'Shared files'  |  Spec: Agile Spec v2.0
"""

import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.ai import llm_client
from app.core import scheduler
from app.core.config import get_settings
from app.core.database import connection
from app.repositories import policy_chunk_repo
from app.schemas import DependencyHealth, HealthOut
from app.services import weather_service

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
def check_weather_api() -> DependencyHealth:
    """One geocoding call, cached 60 s so /health never hammers Open-Meteo."""
    ok, latency = weather_service.ping_geocoding()
    return DependencyHealth(name="weather_api", ok=ok, latency_ms=latency,
                            detail=None if ok else "Open-Meteo geocoding unreachable")


def check_ai_provider() -> DependencyHealth:
    """Configuration only (key + model set): no LLM call, so /health uses no quota."""
    ok, detail = llm_client.is_configured()
    return DependencyHealth(name="ai_provider", ok=ok, detail=detail)


def check_policy_index() -> DependencyHealth:
    """policy_chunks must be filled by scripts/ingest_policy.py."""
    try:
        with connection() as db:
            count, _ = policy_chunk_repo.fingerprint(db)
        return DependencyHealth(name="policy_index", ok=count > 0, detail=f"{count} chunks")
    except Exception as exc:  # noqa: BLE001 - report, never crash /health
        return DependencyHealth(name="policy_index", ok=False, detail=type(exc).__name__)


def check_scheduler() -> DependencyHealth:
    """The scheduler's last run (scheduler.last_run_at) must be within two intervals."""
    settings = get_settings()
    if not settings.scheduler_enabled:
        return DependencyHealth(name="scheduler", ok=True, detail="disabled in .env")
    last = scheduler.last_run_at
    ok = last is not None and datetime.now(timezone.utc) - last < timedelta(minutes=2 * settings.scheduler_interval_minutes)
    return DependencyHealth(name="scheduler", ok=ok, detail=f"last run {last.isoformat() if last else 'never'}")


CHECKS: list[Callable[[], DependencyHealth]] = [
    check_database,
    # --- Piyush/M2 ---
    check_weather_api,
    check_ai_provider,
    check_policy_index,
    check_scheduler,
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

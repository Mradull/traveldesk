"""
asyncio task started in the FastAPI lifespan; runs services/jobs.py every SCHEDULER_INTERVAL_MINUTES.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0  (Technology choices > Scheduler; US-09; Trip rules > Automatic completion)

How it works: when the backend starts, one background task runs every job once, then sleeps for
SCHEDULER_INTERVAL_MINUTES (default 60) and repeats. Each job runs in a worker thread with its own
database transaction, and a failing job is logged without stopping the others. Jobs only run while
the backend is running; the ticket-time check in TicketService covers any missed run.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone

from app.services import jobs

logger = logging.getLogger("traveldesk.scheduler")

# Time of the last completed run (UTC); GET /health uses it for the scheduler check.
last_run_at: datetime | None = None

# Jobs run on every pass, each on its own.
JOBS: list[Callable[[], int]] = [
    # --- Joyal/M1 ---
    jobs.auto_complete_trips,
    jobs.delete_unattached_evidence,
    # --- Piyush/M2 ---
    jobs.expire_idle_sessions,
]


def run_jobs_once() -> dict[str, int | None]:
    """Run every job once; return {job name: rows changed, or None if it failed}."""
    global last_run_at
    results: dict[str, int | None] = {}
    for job in JOBS:
        try:
            results[job.__name__] = job()
        except Exception as exc:  # noqa: BLE001 - one failing job must never stop the others
            results[job.__name__] = None
            logger.error(json.dumps({"event": "scheduled_job_failed", "job": job.__name__,
                                     "error_type": type(exc).__name__}))
    last_run_at = datetime.now(timezone.utc)
    logger.info(json.dumps({"event": "scheduled_jobs_run", "results": results}))
    return results


async def _loop(interval_minutes: int) -> None:
    while True:
        await asyncio.to_thread(run_jobs_once)          # database work off the event loop
        await asyncio.sleep(interval_minutes * 60)


def start(interval_minutes: int) -> asyncio.Task:
    """Start the background loop (called from the FastAPI lifespan)."""
    return asyncio.create_task(_loop(interval_minutes), name="traveldesk-scheduler")


async def stop(task: asyncio.Task | None) -> None:
    """Cancel the loop when the backend shuts down."""
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

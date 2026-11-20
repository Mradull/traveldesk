"""
Scheduled jobs: auto_complete_trips(), delete_unattached_evidence() (Joyal); expire_idle_sessions() (Piyush).
Each job runs independently; one failing never stops the others.

Owner: Joyal (M1) + Piyush (M2), see 'Shared files'  |  Spec: Agile Spec v2.0
"""

from collections.abc import Callable

from sqlalchemy.engine import Connection

from app.core.database import transaction
from app.services import evidence_service, trip_service


def _run(work: Callable[[Connection], int], db: Connection | None) -> int:
    """Run one job in its own transaction (scheduler), or on the caller's connection (tests)."""
    if db is not None:
        return work(db)
    with transaction() as own_db:
        return work(own_db)


# --- Joyal/M1: business jobs ---
def auto_complete_trips(db: Connection | None = None) -> int:
    """Active trips whose start date + 90 days has been reached become Completed (AUTO) [POL-4.3].
    Returns how many trips were completed."""
    return _run(trip_service.auto_complete_trips, db)


def delete_unattached_evidence(db: Connection | None = None) -> int:
    """Receipt photos never attached to an expense line after 24 hours are deleted.
    Returns how many uploads were removed."""
    return _run(evidence_service.delete_unattached, db)


# --- Piyush/M2: expire_idle_sessions() goes here (and is added to core/scheduler.py JOBS) ---

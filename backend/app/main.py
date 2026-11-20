"""
FastAPI app: CORS, request middleware, error handlers, and router registration.
The scheduler lifespan is added with the Joyal scheduler; Piyush only adds the chat router line.

Owner: Joyal (M1) + Piyush (M2), see 'Shared files'  |  Spec: Agile Spec v2.0
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import scheduler
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.routers.auth import me_router, router as auth_router
from app.routers.evidence import router as evidence_router
from app.routers.expenses import router as expenses_router
from app.routers.health import router as health_router
from app.routers.policy import router as policy_router
from app.routers.reports import router as reports_router
from app.routers.tickets import router as tickets_router
from app.routers.trips import router as trips_router

settings = get_settings()
configure_logging(settings.log_level, settings.log_format)      # Joyal/M1: JSON console logs


# --- Joyal/M1: lifespan starts the hourly scheduler (spec > Technology choices > Scheduler) ---
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    current = get_settings()
    task = scheduler.start(current.scheduler_interval_minutes) if current.scheduler_enabled else None
    yield
    await scheduler.stop(task)


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.cors_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    RequestContextMiddleware,
    correlation_header=settings.correlation_header,
)
install_error_handlers(app)

# --- Joyal/M1: authentication and business routers ---
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(me_router, prefix=settings.api_prefix)
app.include_router(trips_router, prefix=settings.api_prefix)
app.include_router(evidence_router, prefix=settings.api_prefix)
app.include_router(tickets_router, prefix=settings.api_prefix)
app.include_router(expenses_router, prefix=settings.api_prefix)
app.include_router(policy_router, prefix=settings.api_prefix)
app.include_router(reports_router, prefix=settings.api_prefix)

# --- Piyush/M2: register the chat router here; do not change M1 middleware or handlers ---

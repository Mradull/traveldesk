"""
FastAPI app: CORS, request middleware, error handlers, and router registration.
The scheduler lifespan is added with the Joyal scheduler; Piyush only adds the chat router line.

Owner: Joyal (M1) + Piyush (M2), see 'Shared files'  |  Spec: Agile Spec v2.0
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.middleware import RequestContextMiddleware
from app.routers.auth import me_router, router as auth_router
from app.routers.trips import router as trips_router

settings = get_settings()
app = FastAPI(title=settings.app_name)

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
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(me_router, prefix=settings.api_prefix)
app.include_router(trips_router, prefix=settings.api_prefix)

# --- Piyush/M2: register the chat router here; do not change M1 middleware or handlers ---

"""
Settings(BaseSettings) read from backend/.env. Grouped by prefix (DB_, JWT_, POLICY_, EVIDENCE_ ... by Joyal;
AI_, OPENROUTER_, EMBEDDING_, RAG_, WEATHER_, CHAT_ ... by Piyush).

Owner: Joyal (M1) + Piyush (M2), see 'Shared files'  |  Spec: Agile Spec v2.0
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application configuration loaded from environment or backend/.env."""

    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "TravelDesk API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    tz: str = "Asia/Kolkata"
    log_level: str = "INFO"
    log_format: str = "json"
    cors_origins: str = "http://localhost:5173"
    company_name: str = "Veridian Global Services"
    assistant_name: str = "Vera"

    database_url: str | None = None
    test_database_url: str | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_recycle_seconds: int = 1800
    db_connect_timeout_seconds: int = 10
    db_statement_timeout_ms: int = 5000

    jwt_secret_key: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    seed_demo_password: SecretStr | None = None

    policy_threshold_airfare: int = 20000
    policy_threshold_lodging: int = 7500
    policy_threshold_meals: int = 1500
    policy_threshold_ground_transport: int = 3000
    policy_threshold_incidentals: int = 1000
    policy_trip_auto_complete_days_after_start: int = 90
    policy_rules_version: str = "VGS-FIN-TE-001 v2.0"

    evidence_max_bytes: int = 5_242_880
    evidence_allowed_mime_types: str = "image/jpeg,image/png,image/webp"
    evidence_unattached_retention_hours: int = 24

    scheduler_enabled: bool = True
    scheduler_interval_minutes: int = 60

    error_log_to_db: bool = True
    error_log_stack_traces: bool = True
    correlation_header: str = "X-Correlation-ID"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one settings instance so environment configuration is loaded once."""
    return Settings()

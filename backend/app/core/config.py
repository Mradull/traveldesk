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

    # ===================== M2 (Piyush) START =====================
    # AI provider (openrouter | gemini | azure). Keys are SecretStr so they never show in logs or repr.
    ai_provider: str = "openrouter"
    ai_timeout_seconds: float = 30
    ai_max_retries: int = 1                 # retried only on timeout / 5xx / connection errors
    ai_temperature: float = 0.2
    ai_max_output_tokens: int = 800
    prompt_version: str = "vera-system-v2.1"
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "nvidia/nemotron-3.5-super-vl:free"
    openrouter_reasoning_enabled: bool = False
    openrouter_app_title: str = "TravelDesk-EY-Capstone"
    gemini_api_key: SecretStr | None = None   # Gemini through its OpenAI-compatible endpoint
    gemini_model: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    # Gemini 3 models always "think"; low = faster answers (minimal | low | medium | high, "" = model default)
    gemini_reasoning_effort: str = "low"
    azure_openai_endpoint: str = ""
    azure_openai_api_key: SecretStr | None = None
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = ""

    # Embeddings + RAG (policy_rules_version is in Joyal's policy block above)
    embedding_provider: str = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384
    policy_document_path: str = "data/expense_policy.txt"   # relative to backend/
    rag_top_k: int = 4
    rag_min_similarity: float = 0.35

    # Weather (Open-Meteo), used only by Vera's tool
    weather_geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    weather_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: float = 8
    weather_forecast_horizon_days: int = 16
    weather_cache_ttl_minutes: int = 180
    weather_ambiguity_min_population: int = 100000

    # Chat (Vera)
    chat_idle_timeout_minutes: int = 60
    chat_history_turns: int = 8
    chat_context_token_budget: int = 6000
    chat_max_tool_calls_per_turn: int = 4
    chat_rate_limit_per_minute: int = 10
    chat_max_message_chars: int = 1000

    # Evals
    eval_use_live_llm: bool = False
    # ===================== M2 (Piyush) END =======================

    # ===================== M3 (Mradul) START =====================
    # Receipt verification (Spec v2.1). OFF unless RECEIPT_CHECK_ENABLED=true, so tests and
    # machines without the keys behave exactly as before.
    receipt_check_enabled: bool = False
    receipt_vision_model: str = ""              # "" = use OPENROUTER_MODEL (Nemotron VL reads images)
    receipt_amount_tolerance_pct: float = 1.0   # receipt total may differ by 1% ...
    receipt_amount_tolerance_min_inr: float = 10.0   # ... or Rs 10, whichever is larger
    receipt_date_tolerance_days: int = 1
    receipt_ai_generated_threshold: float = 0.5  # Sightengine score at or above this -> FAIL
    sightengine_api_user: str = ""
    sightengine_api_secret: SecretStr | None = None
    sightengine_url: str = "https://api.sightengine.com/1.0/check.json"
    sightengine_timeout_seconds: float = 10
    # ===================== M3 (Mradul) END =======================


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one settings instance so environment configuration is loaded once."""
    return Settings()

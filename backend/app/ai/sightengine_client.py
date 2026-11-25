"""
ai/sightengine_client.py - asks Sightengine whether a receipt photo is AI-generated or edited.

Owner: Mradul (M3)  |  Spec: Agile Spec v2.1 > Receipt verification

One call per photo (model "genai"), timeout SIGHTENGINE_TIMEOUT_SECONDS. Returns a score 0..1, or
None when Sightengine is not configured or fails: the authenticity check is then NOT_CHECKED and
the rest of the receipt check still runs. The API secret is read from .env and never logged.
"""
import logging

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)


class SightengineError(Exception):
    """Sightengine did not give a usable answer (code is stored in receipt_checks.error_code)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def is_configured() -> bool:
    settings = get_settings()
    secret = settings.sightengine_api_secret.get_secret_value() if settings.sightengine_api_secret else ""
    return bool(settings.sightengine_api_user) and bool(secret) and "<" not in secret and "<" not in settings.sightengine_api_user


def ai_generated_score(content: bytes, mime_type: str) -> float | None:
    """Probability (0..1) that the image was generated or edited by AI. None when not configured.
    Raises SightengineError on a failed call, so the caller can record why."""
    if not is_configured():
        return None
    settings = get_settings()
    try:
        response = httpx.post(
            settings.sightengine_url,
            data={
                "models": "genai",
                "api_user": settings.sightengine_api_user,
                "api_secret": settings.sightengine_api_secret.get_secret_value(),
            },
            files={"media": ("receipt", content, mime_type)},
            timeout=settings.sightengine_timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise SightengineError("SIGHTENGINE_TIMEOUT") from exc
    except httpx.TransportError as exc:
        raise SightengineError("SIGHTENGINE_CONNECTION_FAILED") from exc
    if response.status_code == 429:
        raise SightengineError("SIGHTENGINE_RATE_LIMITED")
    if response.status_code >= 400:
        raise SightengineError(f"SIGHTENGINE_HTTP_{response.status_code}")
    try:
        body = response.json()
        if body.get("status") != "success":
            raise SightengineError(f"SIGHTENGINE_{(body.get('error') or {}).get('type', 'ERROR')}".upper())
        score = float(body["type"]["ai_generated"])
    except (ValueError, KeyError, TypeError) as exc:
        raise SightengineError("SIGHTENGINE_INVALID_RESPONSE") from exc
    return min(max(score, 0.0), 1.0)

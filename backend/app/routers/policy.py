"""
GET /policy/rules (PolicyRulesOut) for limits shown next to the ticket form.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.schemas import MAX_LINE_AMOUNT_INR, CurrentUser, PolicyRulesOut
from app.services.policy_engine import PolicyConfig

router = APIRouter(prefix="/policy", tags=["policy"])


@router.get("/rules", response_model=PolicyRulesOut)
def policy_rules(user: Annotated[CurrentUser, Depends(get_current_user)]) -> PolicyRulesOut:
    """Review thresholds, hard cap and photo limits from .env, so the form shows the same numbers."""
    settings = get_settings()
    config = PolicyConfig.from_settings(settings)
    return PolicyRulesOut(
        rules_version=config.rules_version,
        review_thresholds_inr=config.thresholds,
        hard_cap_per_line_inr=MAX_LINE_AMOUNT_INR,
        evidence_max_bytes=settings.evidence_max_bytes,
        evidence_mime_types=[m.strip() for m in settings.evidence_allowed_mime_types.split(",") if m.strip()],
        trip_auto_complete_days_after_start=settings.policy_trip_auto_complete_days_after_start,
    )

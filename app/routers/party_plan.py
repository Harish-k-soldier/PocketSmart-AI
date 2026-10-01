"""POST /api/party-plan — Party Planner API."""

import logging

from fastapi import APIRouter, Depends, Request

from app.config import Settings, get_settings
from app.models.common import InsufficientBudgetBody
from app.models.party import PartyPlanRequest, PartyPlanResponse
from app.services.gemini import AINotConfiguredError
from app.services.planners import build_party_plan

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/party-plan", response_model=PartyPlanResponse | InsufficientBudgetBody)
async def party_plan(
    request: PartyPlanRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
):
    if not settings.ai_configured:
        raise AINotConfiguredError(
            "AI service is not configured. Set GEMINI_API_KEY or enable USE_MOCK_AI."
        )
    return await build_party_plan(request, settings)

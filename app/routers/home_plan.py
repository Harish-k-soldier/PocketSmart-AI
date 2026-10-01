"""POST /api/home-plan — Home Budget Planner API."""

import logging

from fastapi import APIRouter, Depends, Request

from app.config import Settings, get_settings
from app.models.common import ErrorBody, ErrorResponse, InsufficientBudgetBody
from app.models.home import HomePlanRequest, HomePlanResponse
from app.services.gemini import AINotConfiguredError
from app.services.planners import build_home_plan

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/home-plan", response_model=HomePlanResponse | InsufficientBudgetBody)
async def home_plan(
    request: HomePlanRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
):
    if not settings.ai_configured:
        raise AINotConfiguredError(
            "AI service is not configured. Set GEMINI_API_KEY or enable USE_MOCK_AI."
        )
    return await build_home_plan(request, settings)

"""GET /api/health — liveness probe. Never exposes the API key."""

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter()


@router.get("/api/health")
async def health(settings: Settings = Depends(get_settings)):
    return {
        "status": "ok",
        "model": settings.gemini_model,
        "ai_configured": settings.ai_configured,
        "mock": settings.use_mock_ai,
    }

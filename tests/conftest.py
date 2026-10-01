import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("USE_MOCK_AI", "true")
os.environ.setdefault("GEMINI_API_KEY", "")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def test_settings():
    return Settings(
        gemini_api_key="",
        gemini_model="gemini-2.5-flash",
        use_mock_ai=True,
        ai_timeout_seconds=30,
        ai_max_retries=1,
        max_upload_mb=5,
        rate_limit_per_minute=1000,
        app_env="development",
    )


@pytest.fixture
async def client(test_settings):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def patch_gemini(monkeypatch):
    """Monkeypatch the generate_structured reference used by planners."""
    def apply(responses):
        import app.services.planners as planners_svc
        calls = {"count": 0}

        async def fake(system_prompt, user_prompt, schema, image_bytes=None, mime_type=None, settings=None):
            idx = min(calls["count"], len(responses) - 1)
            calls["count"] += 1
            resp = responses[idx]
            if isinstance(resp, Exception):
                raise resp
            return resp

        monkeypatch.setattr(planners_svc, "generate_structured", fake)
        return calls

    return apply

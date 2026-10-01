"""Gemini service: the only place that talks to the Google Gen AI SDK.

All calls go through generate_structured(), which enforces structured JSON
output, defensive parsing, timeouts, and retries. Python never trusts numbers
from the model: it only uses the model's item picks and short text reasons.
"""

import asyncio
import json
import logging
import re
from typing import Any, Optional, Type

from pydantic import BaseModel

from app.config import Settings, get_settings

log = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class AINotConfiguredError(Exception):
    """Raised when no API key is set and mock mode is off."""


class AIUnavailableError(Exception):
    """Raised when Gemini cannot be reached or keeps failing."""


class AIResponseError(Exception):
    """Raised when the response cannot be parsed into the expected schema."""


class AIAuthError(Exception):
    """Raised on authentication/permission errors. Never retried."""


_AUTH_ERROR_MARKERS = (
    "api_key", "api key", "permission", "unauthenticated", "forbidden",
    "401", "403", "quota", "invalid api key",
)

_client = None
_client_failed = False


def _import_genai():
    try:
        from google import genai  # noqa: PLC0415
        from google.genai import types  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment issue
        raise AIUnavailableError(
            "google-genai package is not installed. Run: pip install -r requirements.txt"
        ) from exc
    return genai, types


def _get_client(settings: Settings):
    """Create the genai.Client lazily, only when needed and configured."""
    global _client, _client_failed
    if _client is not None:
        return _client
    if _client_failed:
        raise AINotConfiguredError("AI service is not configured.")
    if not settings.gemini_api_key:
        raise AINotConfiguredError("AI service is not configured.")
    genai, _ = _import_genai()
    _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _is_auth_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _AUTH_ERROR_MARKERS)


def _parse_response_text(text: Optional[str], schema: Type[BaseModel]) -> dict[str, Any]:
    if text is None or not text.strip():
        raise AIResponseError("Gemini returned empty text")
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AIResponseError(f"Gemini returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AIResponseError("Gemini response was not a JSON object")
    try:
        return schema.model_validate(parsed).model_dump()
    except Exception as exc:
        raise AIResponseError(f"Gemini response failed schema validation: {exc}") from exc


async def generate_structured(
    system_prompt: str,
    user_prompt: str,
    schema: Type[BaseModel],
    image_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> dict[str, Any]:
    """Call Gemini for structured JSON output and return a validated dict.

    Retries up to settings.ai_max_retries on transient failures with a 1s
    backoff. Auth/permission errors raise AIAuthError immediately.
    """
    settings = settings or get_settings()

    if settings.use_mock_ai:
        from app.services import mock_ai
        return await mock_ai.generate_structured(
            system_prompt, user_prompt, schema, image_bytes, mime_type
        )

    client = _get_client(settings)
    _, types = _import_genai()

    contents: Any = user_prompt
    if image_bytes is not None and mime_type is not None:
        contents = [
            user_prompt,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ]

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=schema,
        temperature=0.4,
        max_output_tokens=4096,
    )

    max_attempts = 1 + max(0, settings.ai_max_retries)
    last_error: Optional[BaseException] = None

    def _call() -> Any:
        # GOOGLE API CALL: Gemini generateContent (gemini.generate_structured)
        return client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=config,
        )

    for attempt in range(1, max_attempts + 1):
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(_call),
                timeout=settings.ai_timeout_seconds,
            )
            return _parse_response_text(getattr(response, "text", None), schema)
        except AIAuthError:
            raise
        except AIResponseError as exc:
            last_error = exc
            log.warning("Gemini response parse failed (attempt %d/%d): %s", attempt, max_attempts, exc)
        except (asyncio.TimeoutError, TimeoutError) as exc:
            last_error = exc
            log.warning("Gemini call timed out (attempt %d/%d)", attempt, max_attempts)
        except Exception as exc:  # SDK raises a variety of error types
            if _is_auth_error(exc):
                log.error("Gemini auth/permission error, not retrying: %s", type(exc).__name__)
                raise AIAuthError(f"Gemini authentication failed: {type(exc).__name__}") from exc
            last_error = exc
            log.warning("Gemini call failed (attempt %d/%d): %s: %s", attempt, max_attempts, type(exc).__name__, exc)
        if attempt < max_attempts:
            await asyncio.sleep(1)

    raise AIUnavailableError(f"Gemini unavailable after {max_attempts} attempt(s): {last_error}")

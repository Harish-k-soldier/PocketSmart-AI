import pytest
import asyncio
import json


from app.config import Settings
from app.services import gemini as gemini_svc
from app.services.gemini import (
    AIAuthError,
    AINotConfiguredError,
    AIResponseError,
    AIUnavailableError,
)



class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = 0

    def generate_content(self, model=None, contents=None, config=None):
        self.calls += 1
        result = self.behavior(self.calls)
        if isinstance(result, Exception):
            raise result
        return result


class FakeClient:
    def __init__(self, behavior):
        self.models = FakeModels(behavior)


def test_fenced_json_parsed():
    text = '```json\n{"hello": "world"}\n```'
    result = gemini_svc._parse_response_text(text, _DummySchema)
    assert result == {"hello": "world"}


def test_plain_json_parsed():
    result = gemini_svc._parse_response_text('{"a": 1}', _DummySchema)
    assert result == {"a": 1}


def test_empty_text_raises():
    with pytest.raises(AIResponseError):
        gemini_svc._parse_response_text("", _DummySchema)
    with pytest.raises(AIResponseError):
        gemini_svc._parse_response_text(None, _DummySchema)


def test_invalid_json_raises():
    with pytest.raises(AIResponseError):
        gemini_svc._parse_response_text("not json", _DummySchema)


from pydantic import BaseModel, ConfigDict


class _DummySchema(BaseModel):
    model_config = ConfigDict(extra="allow")


def _settings(retries=1, timeout=30):
    return Settings(
        gemini_api_key="test-key",
        gemini_model="gemini-2.5-flash",
        use_mock_ai=False,
        ai_timeout_seconds=timeout,
        ai_max_retries=retries,
    )


async def test_not_configured_raises(monkeypatch):
    monkeypatch.setattr(gemini_svc, "_client", None)
    monkeypatch.setattr(gemini_svc, "_client_failed", False)
    settings = _settings()
    settings.gemini_api_key = ""
    with pytest.raises(AINotConfiguredError):
        await gemini_svc.generate_structured("sys", "user", _DummySchema, settings=settings)


async def test_retry_happens_exactly_once(monkeypatch):
    monkeypatch.setattr(gemini_svc, "_client", None)
    monkeypatch.setattr(gemini_svc, "_client_failed", False)
    calls = {"n": 0}

    def behavior(n):
        calls["n"] += 1
        if n == 1:
            raise TimeoutError("timed out")
        return FakeResponse('{"ok": true}')

    monkeypatch.setattr(gemini_svc, "_get_client", lambda settings: FakeClient(behavior))
    settings = _settings(retries=1)
    result = await gemini_svc.generate_structured("sys", "user", _DummySchema, settings=settings)
    assert result is not None
    assert calls["n"] == 2


async def test_auth_error_not_retried(monkeypatch):
    monkeypatch.setattr(gemini_svc, "_client", None)
    monkeypatch.setattr(gemini_svc, "_client_failed", False)
    calls = {"n": 0}

    def behavior(n):
        calls["n"] += 1
        raise Exception("403 permission denied: api key invalid")

    monkeypatch.setattr(gemini_svc, "_get_client", lambda settings: FakeClient(behavior))
    settings = _settings(retries=2)
    with pytest.raises(AIAuthError):
        await gemini_svc.generate_structured("sys", "user", _DummySchema, settings=settings)
    assert calls["n"] == 1


async def test_timeout_converted_to_unavailable(monkeypatch):
    monkeypatch.setattr(gemini_svc, "_client", None)
    monkeypatch.setattr(gemini_svc, "_client_failed", False)

    def behavior(n):
        raise TimeoutError("timed out")

    monkeypatch.setattr(gemini_svc, "_get_client", lambda settings: FakeClient(behavior))
    settings = _settings(retries=0)
    with pytest.raises(AIUnavailableError):
        await gemini_svc.generate_structured("sys", "user", _DummySchema, settings=settings)


async def test_success_no_retry(monkeypatch):
    monkeypatch.setattr(gemini_svc, "_client", None)
    monkeypatch.setattr(gemini_svc, "_client_failed", False)
    calls = {"n": 0}

    def behavior(n):
        calls["n"] += 1
        return FakeResponse('{"ok": true}')

    monkeypatch.setattr(gemini_svc, "_get_client", lambda settings: FakeClient(behavior))
    settings = _settings(retries=1)
    result = await gemini_svc.generate_structured("sys", "user", _DummySchema, settings=settings)
    assert result is not None
    assert calls["n"] == 1

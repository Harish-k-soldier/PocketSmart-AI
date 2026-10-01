"""Application settings loaded from environment / .env via pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    use_mock_ai: bool = False
    ai_timeout_seconds: int = 30
    ai_max_retries: int = 1
    max_upload_mb: int = 5
    rate_limit_per_minute: int = 20
    app_env: str = "development"

    @property
    def ai_configured(self) -> bool:
        return bool(self.gemini_api_key) or self.use_mock_ai


@lru_cache
def get_settings() -> Settings:
    return Settings()

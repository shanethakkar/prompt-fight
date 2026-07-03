"""Runtime settings (secrets/env), separate from game balance in config/balance.json.

The Anthropic API key lives ONLY on the backend and is loaded from backend/.env.
It is optional in M0 (the SDK isn't called yet) and becomes required in M2.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        extra="ignore",
    )

    anthropic_api_key: str | None = None


def get_settings() -> Settings:
    return Settings()

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process settings. Project-level overrides are loaded separately from PostgreSQL."""

    model_config = SettingsConfigDict(
        env_prefix="AUTODEV_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    api_base_url: str = "http://127.0.0.1:8000"
    database_url: str = "postgresql+asyncpg://autodev:autodev@localhost:5432/autodev"
    redis_url: str = "redis://localhost:6379/0"
    ollama_base_url: str = "http://localhost:11434"
    litellm_base_url: str = "http://localhost:4000"
    agentmemory_base_url: str = "http://localhost:3111"
    codex_executable: str = "codex"
    credential_key: SecretStr | None = None
    max_codex_workers: int = Field(default=2, ge=1, le=32)
    allow_paid_models: bool = False
    max_cloud_cost_usd_day: float = Field(default=0.0, ge=0.0)
    max_cloud_cost_usd_month: float = Field(default=0.0, ge=0.0)
    project_root: Path = Field(default_factory=Path.cwd)


@lru_cache
def get_settings() -> Settings:
    return Settings()

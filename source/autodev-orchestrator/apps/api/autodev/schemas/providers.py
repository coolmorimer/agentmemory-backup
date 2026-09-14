from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class ProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["ollama", "openai_compatible"]
    enabled: bool
    base_url: str = Field(min_length=1, max_length=1000)
    api_key_env: str | None = Field(default=None, max_length=120)
    api_key: SecretStr | None = None
    billing_mode: Literal["local", "free", "paid", "gateway"]
    accepts_private_code: bool = False
    timeout_seconds: float = Field(default=60, gt=0, le=600)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("base_url must use http or https")
        return normalized

    @field_validator("api_key_env")
    @classmethod
    def validate_environment_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized.replace("_", "A").isalnum() or not normalized[0].isalpha():
            raise ValueError("api_key_env must be an environment variable name")
        return normalized.upper()


class ModelSelectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=300)

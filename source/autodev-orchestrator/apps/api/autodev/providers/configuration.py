from __future__ import annotations

from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from autodev.providers.base import LLMProvider
from autodev.providers.ollama import OllamaProvider
from autodev.providers.openai_compatible import OpenAICompatibleProvider
from autodev.providers.registry import ProviderRegistry


class ProviderConfigurationError(ValueError):
    pass


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    kind: Literal["ollama", "openai_compatible"] = "openai_compatible"
    base_url: str | None = None
    api_key_env: str | None = None
    billing_mode: Literal["local", "free", "paid", "gateway"] = "free"
    accepts_private_code: bool = False
    timeout_seconds: float = Field(default=60, gt=0, le=600)


class ProviderCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: dict[str, ProviderSettings]


def load_provider_catalog(path: Path) -> ProviderCatalog:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return ProviderCatalog.model_validate(payload)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as error:
        raise ProviderConfigurationError(f"invalid provider configuration: {error}") from error


def build_provider_registry(
    catalog: ProviderCatalog,
    *,
    clients: dict[str, httpx.AsyncClient] | None = None,
) -> ProviderRegistry:
    registry = ProviderRegistry()
    for name, settings in catalog.providers.items():
        if not settings.enabled:
            continue
        if not settings.base_url:
            raise ProviderConfigurationError(f"enabled provider has no base_url: {name}")
        client = clients.get(name) if clients else None
        if settings.kind == "ollama":
            if name != "ollama":
                raise ProviderConfigurationError(
                    "the Ollama adapter must use provider name 'ollama'"
                )
            provider: LLMProvider = OllamaProvider(
                settings.base_url,
                client=client,
                timeout_seconds=settings.timeout_seconds,
            )
        else:
            provider = OpenAICompatibleProvider(
                name=name,
                base_url=settings.base_url,
                api_key_env=settings.api_key_env,
                client=client,
                timeout_seconds=settings.timeout_seconds,
            )
        registry.register(provider)
    return registry

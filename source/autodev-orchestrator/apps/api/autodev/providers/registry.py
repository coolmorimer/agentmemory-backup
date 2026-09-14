from __future__ import annotations

from autodev.providers.base import LLMProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"provider already registered: {provider.name}")
        self._providers[provider.name] = provider

    def get(self, name: str) -> LLMProvider:
        try:
            return self._providers[name]
        except KeyError as error:
            raise LookupError(f"provider is not registered: {name}") from error

    def names(self) -> list[str]:
        return sorted(self._providers)

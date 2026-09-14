from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class ModelMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ModelRequest(BaseModel):
    model: str
    messages: list[ModelMessage]
    temperature: float = Field(default=0, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)
    response_schema: dict[str, Any] | None = None


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelResponse(BaseModel):
    provider: str
    model: str
    content: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: str | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)


class ProviderHealth(BaseModel):
    available: bool
    latency_seconds: float | None = None
    detail: str | None = None


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        retryable: bool,
        status_code: int | None = None,
        response_headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable
        self.status_code = status_code
        self.response_headers = response_headers or {}


class RateLimitError(ProviderError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        retry_after_seconds: float | None,
        response_headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            message,
            provider=provider,
            retryable=True,
            status_code=429,
            response_headers=response_headers,
        )
        self.retry_after_seconds = retry_after_seconds


class LLMProvider(Protocol):
    name: str

    async def complete(self, request: ModelRequest) -> ModelResponse: ...

    async def health(self) -> ProviderHealth: ...

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from autodev.providers.base import (
    ModelRequest,
    ModelResponse,
    ProviderError,
    ProviderHealth,
    TokenUsage,
)
from autodev.providers.http import raise_provider_error


def ollama_model_name(model: str) -> str:
    return model.removeprefix("ollama/")


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 300,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout_seconds

    async def complete(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, object] = {
            "model": ollama_model_name(request.model),
            "messages": [message.model_dump(mode="json") for message in request.messages],
            "stream": False,
            "options": {"temperature": request.temperature},
        }
        if request.response_schema:
            payload["format"] = request.response_schema
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns_client = self._client is None
        try:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
            raise_provider_error(response, provider=self.name)
            body = response.json()
            return ModelResponse(
                provider=self.name,
                model=str(body.get("model") or request.model),
                content=str(body["message"]["content"]),
                finish_reason="stop" if body.get("done") else None,
                usage=TokenUsage(
                    prompt_tokens=int(body.get("prompt_eval_count", 0)),
                    completion_tokens=int(body.get("eval_count", 0)),
                    total_tokens=int(body.get("prompt_eval_count", 0))
                    + int(body.get("eval_count", 0)),
                ),
                response_headers={key: value for key, value in response.headers.items()},
            )
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise ProviderError(
                f"ollama transport error: {type(error).__name__}",
                provider=self.name,
                retryable=True,
            ) from error
        except (KeyError, TypeError, ValueError) as error:
            raise ProviderError(
                "ollama returned an invalid response envelope",
                provider=self.name,
                retryable=True,
            ) from error
        finally:
            if owns_client:
                await client.aclose()

    async def health(self) -> ProviderHealth:
        started = time.monotonic()
        try:
            await self.list_models()
            return ProviderHealth(available=True, latency_seconds=time.monotonic() - started)
        except ProviderError as error:
            return ProviderHealth(
                available=False,
                latency_seconds=time.monotonic() - started,
                detail=str(error),
            )

    async def list_models(self) -> set[str]:
        client = self._client or httpx.AsyncClient(timeout=min(self._timeout, 10))
        owns_client = self._client is None
        try:
            response = await client.get(f"{self._base_url}/api/tags")
            raise_provider_error(response, provider=self.name)
            return {
                str(item["name"])
                for item in response.json().get("models", [])
                if isinstance(item, dict) and item.get("name")
            }
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise ProviderError(
                f"ollama transport error: {type(error).__name__}",
                provider=self.name,
                retryable=True,
            ) from error
        finally:
            if owns_client:
                await client.aclose()


class LocalModelManager:
    """Serialize large local inference and verify model presence before dispatch."""

    def __init__(self, provider: OllamaProvider, *, max_gpu_concurrency: int = 1) -> None:
        if max_gpu_concurrency < 1:
            raise ValueError("max_gpu_concurrency must be positive")
        self._provider = provider
        self._semaphore = asyncio.Semaphore(max_gpu_concurrency)

    async def available(self, model: str) -> bool:
        names = await self._provider.list_models()
        requested = ollama_model_name(model)
        return requested in names or f"{requested}:latest" in names

    @asynccontextmanager
    async def inference_slot(self, model: str) -> AsyncIterator[None]:
        if not await self.available(model):
            raise ProviderError(
                f"local model is not installed: {ollama_model_name(model)}",
                provider="ollama",
                retryable=False,
            )
        async with self._semaphore:
            yield

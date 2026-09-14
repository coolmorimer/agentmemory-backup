from __future__ import annotations

import os
import time

import httpx

from autodev.providers.base import (
    ModelRequest,
    ModelResponse,
    ProviderError,
    ProviderHealth,
    TokenUsage,
)
from autodev.providers.http import raise_provider_error


class OpenAICompatibleProvider:
    """Adapter for LiteLLM and configured OpenAI-compatible provider endpoints."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key_env: str | None = None,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 60,
    ) -> None:
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._api_key_env = api_key_env
        self._api_key = api_key
        self._client = client
        self._timeout = timeout_seconds

    async def complete(self, request: ModelRequest) -> ModelResponse:
        headers = {"content-type": "application/json"}
        if self._api_key_env or self._api_key:
            api_key = self._api_key or os.getenv(self._api_key_env or "")
            if not api_key:
                raise ProviderError(
                    f"credential environment variable is not set: {self._api_key_env}",
                    provider=self.name,
                    retryable=False,
                )
            headers["authorization"] = f"Bearer {api_key}"
        payload: dict[str, object] = {
            "model": request.model,
            "messages": [message.model_dump(mode="json") for message in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.response_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "autodev_output",
                    "strict": True,
                    "schema": request.response_schema,
                },
            }
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns_client = self._client is None
        try:
            response = await client.post(
                f"{self._base_url}/chat/completions", json=payload, headers=headers
            )
            raise_provider_error(response, provider=self.name)
            body = response.json()
            choice = body["choices"][0]
            usage = body.get("usage") or {}
            return ModelResponse(
                provider=self.name,
                model=str(body.get("model") or request.model),
                content=str(choice["message"]["content"]),
                finish_reason=choice.get("finish_reason"),
                usage=TokenUsage(
                    prompt_tokens=int(usage.get("prompt_tokens", 0)),
                    completion_tokens=int(usage.get("completion_tokens", 0)),
                    total_tokens=int(usage.get("total_tokens", 0)),
                ),
                response_headers={key: value for key, value in response.headers.items()},
            )
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise ProviderError(
                f"{self.name} transport error: {type(error).__name__}",
                provider=self.name,
                retryable=True,
            ) from error
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderError(
                f"{self.name} returned an invalid response envelope",
                provider=self.name,
                retryable=True,
            ) from error
        finally:
            if owns_client:
                await client.aclose()

    async def health(self) -> ProviderHealth:
        client = self._client or httpx.AsyncClient(timeout=min(self._timeout, 10))
        owns_client = self._client is None
        started = time.monotonic()
        try:
            response = await client.get(
                f"{self._base_url}/models", headers=self._authorization_headers()
            )
            raise_provider_error(response, provider=self.name)
            return ProviderHealth(
                available=True,
                latency_seconds=time.monotonic() - started,
                detail=f"HTTP {response.status_code}",
            )
        except (httpx.HTTPError, ProviderError) as error:
            return ProviderHealth(
                available=False,
                latency_seconds=time.monotonic() - started,
                detail=str(error),
            )
        finally:
            if owns_client:
                await client.aclose()

    async def list_models(self) -> set[str]:
        client = self._client or httpx.AsyncClient(timeout=min(self._timeout, 30))
        owns_client = self._client is None
        try:
            response = await client.get(
                f"{self._base_url}/models", headers=self._authorization_headers()
            )
            raise_provider_error(response, provider=self.name)
            payload = response.json()
            return {
                str(item["id"])
                for item in payload.get("data", [])
                if isinstance(item, dict) and item.get("id")
            }
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise ProviderError(
                f"{self.name} transport error: {type(error).__name__}",
                provider=self.name,
                retryable=True,
            ) from error
        except (TypeError, ValueError) as error:
            raise ProviderError(
                f"{self.name} returned an invalid models envelope",
                provider=self.name,
                retryable=True,
            ) from error
        finally:
            if owns_client:
                await client.aclose()

    def _authorization_headers(self) -> dict[str, str]:
        api_key = self._api_key or os.getenv(self._api_key_env or "")
        return {"authorization": f"Bearer {api_key}"} if api_key else {}

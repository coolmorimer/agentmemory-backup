from __future__ import annotations

import json

import httpx
import pytest

from autodev.providers.base import ModelMessage, ModelRequest, RateLimitError
from autodev.providers.ollama import LocalModelManager, OllamaProvider
from autodev.providers.openai_compatible import OpenAICompatibleProvider


async def test_openai_compatible_completion_uses_structured_output() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert body["response_format"]["type"] == "json_schema"
        return httpx.Response(
            200,
            json={
                "model": "fixture-model",
                "choices": [{"message": {"content": '{"answer":"ok"}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            name="fixture", base_url="https://example.test/v1", client=client
        )
        response = await provider.complete(
            ModelRequest(
                model="fixture-model",
                messages=[ModelMessage(role="user", content="respond")],
                response_schema={"type": "object"},
            )
        )

    assert response.content == '{"answer":"ok"}'
    assert response.usage.total_tokens == 7


async def test_openai_compatible_surfaces_rate_limit_metadata() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow down", headers={"retry-after": "12"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            name="fixture", base_url="https://example.test/v1", client=client
        )
        with pytest.raises(RateLimitError) as error:
            await provider.complete(
                ModelRequest(
                    model="fixture-model",
                    messages=[ModelMessage(role="user", content="respond")],
                )
            )

    assert error.value.retry_after_seconds == 12


async def test_openai_compatible_uses_api_key_for_models_and_rejects_unauthorized() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["authorization"] == "Bearer placeholder-test-key"
        return httpx.Response(401, text="invalid key")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            name="openrouter",
            base_url="https://openrouter.test/v1",
            api_key="placeholder-test-key",
            client=client,
        )
        health = await provider.health()

    assert health.available is False
    assert "HTTP 401" in (health.detail or "")
    assert calls == 1


async def test_ollama_model_manager_checks_presence_and_completion() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5-coder:7b"}]})
        body = json.loads(request.content)
        assert request.url.path == "/api/chat"
        assert body["model"] == "qwen2.5-coder:7b"
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "message": {"role": "assistant", "content": "done"},
                "done": True,
                "prompt_eval_count": 2,
                "eval_count": 1,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaProvider("http://ollama.test", client=client)
        manager = LocalModelManager(provider)
        assert await manager.available("ollama/qwen2.5-coder:7b")
        async with manager.inference_slot("ollama/qwen2.5-coder:7b"):
            response = await provider.complete(
                ModelRequest(
                    model="ollama/qwen2.5-coder:7b",
                    messages=[ModelMessage(role="user", content="work")],
                )
            )

    assert response.content == "done"
    assert response.usage.total_tokens == 3


async def test_ollama_missing_model_is_reported_without_generation() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        manager = LocalModelManager(OllamaProvider("http://ollama.test", client=client))
        assert await manager.available("ollama/qwen2.5-coder:7b") is False

    assert calls == 1

from __future__ import annotations

from pydantic import BaseModel

from autodev.providers.base import ModelRequest, ModelResponse, ProviderHealth
from autodev.providers.structured import complete_structured


class Output(BaseModel):
    answer: str


class SequenceProvider:
    def __init__(self, name: str, responses: list[str]) -> None:
        self.name = name
        self.responses = responses
        self.calls = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        assert request.response_schema is not None
        response = self.responses[self.calls]
        self.calls += 1
        return ModelResponse(provider=self.name, model=request.model, content=response)

    async def health(self) -> ProviderHealth:
        return ProviderHealth(available=True)


async def test_invalid_json_gets_one_repair_attempt() -> None:
    provider = SequenceProvider("first", ["not-json", '{"answer":"repaired"}'])

    result = await complete_structured([provider], ModelRequest(model="model", messages=[]), Output)

    assert result.answer == "repaired"
    assert provider.calls == 2


async def test_fallback_provider_is_used_after_failed_repair() -> None:
    first = SequenceProvider("first", ["bad", '{"wrong":true}'])
    second = SequenceProvider("second", ['{"answer":"fallback"}'])

    result = await complete_structured(
        [first, second], ModelRequest(model="model", messages=[]), Output
    )

    assert result.answer == "fallback"
    assert first.calls == 2
    assert second.calls == 1

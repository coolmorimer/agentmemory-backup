from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from autodev.providers.base import LLMProvider, ModelMessage, ModelRequest, ProviderError


class StructuredOutputError(RuntimeError):
    def __init__(self, failures: list[str]) -> None:
        super().__init__("structured output failed: " + "; ".join(failures))
        self.failures = failures


async def complete_structured[OutputT: BaseModel](
    providers: Sequence[LLMProvider],
    request: ModelRequest,
    output_type: type[OutputT],
) -> OutputT:
    schema = output_type.model_json_schema()
    failures: list[str] = []
    for provider in providers:
        provider_request = request.model_copy(update={"response_schema": schema})
        for attempt in range(2):
            if attempt == 1:
                provider_request = provider_request.model_copy(
                    update={
                        "messages": [
                            *provider_request.messages,
                            ModelMessage(
                                role="user",
                                content=(
                                    "The prior response failed schema validation. "
                                    "Return only valid JSON matching the supplied schema."
                                ),
                            ),
                        ]
                    }
                )
            try:
                response = await provider.complete(provider_request)
                return output_type.model_validate(json.loads(response.content))
            except (json.JSONDecodeError, ValidationError) as error:
                failures.append(f"{provider.name} attempt {attempt + 1}: {type(error).__name__}")
            except ProviderError as error:
                failures.append(f"{provider.name} attempt {attempt + 1}: {error}")
                if not error.retryable:
                    break
    raise StructuredOutputError(failures)

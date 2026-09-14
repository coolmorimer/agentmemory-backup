from __future__ import annotations

import httpx

from autodev.providers.base import ProviderError, RateLimitError


def raise_provider_error(response: httpx.Response, *, provider: str) -> None:
    if response.status_code < 400:
        return
    detail = response.text[-2000:]
    if response.status_code == 429:
        raw_retry = response.headers.get("retry-after")
        try:
            retry_after = float(raw_retry) if raw_retry is not None else None
        except ValueError:
            retry_after = None
        raise RateLimitError(
            f"{provider} rate limited request: {detail}",
            provider=provider,
            retry_after_seconds=retry_after,
            response_headers=dict(response.headers),
        )
    raise ProviderError(
        f"{provider} request failed with HTTP {response.status_code}: {detail}",
        provider=provider,
        retryable=response.status_code >= 500 or response.status_code in {408, 409},
        status_code=response.status_code,
        response_headers=dict(response.headers),
    )

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autodev.db.models import ModelHealthRecord, ModelUsageRecord, ProviderQuotaSnapshot
from autodev.providers.base import ModelRequest, ModelResponse, ProviderError, RateLimitError
from autodev.providers.registry import ProviderRegistry
from autodev.routing.models import BillingMode, HealthState
from autodev.routing.quota import QuotaPolicy, QuotaSnapshot
from autodev.security.redaction import Redactor


class AllProvidersUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderCandidate:
    provider: str
    model: str
    billing_mode: BillingMode = BillingMode.FREE


def quota_from_headers(headers: dict[str, str], *, now: datetime | None = None) -> QuotaSnapshot:
    normalized = {key.casefold(): value.strip() for key, value in headers.items()}
    current = now or datetime.now(UTC)
    return QuotaSnapshot(
        requests_remaining=_first_int(
            normalized,
            "x-ratelimit-remaining-requests",
            "ratelimit-remaining",
            "x-rate-limit-remaining",
        ),
        tokens_remaining=_first_int(
            normalized,
            "x-ratelimit-remaining-tokens",
            "x-ratelimit-token-remaining",
        ),
        reset_at=_parse_reset(
            normalized.get("x-ratelimit-reset-requests")
            or normalized.get("ratelimit-reset")
            or normalized.get("x-rate-limit-reset"),
            current,
        ),
        source="headers",
    )


def _first_int(headers: dict[str, str], *names: str) -> int | None:
    for name in names:
        value = headers.get(name)
        if value is None:
            continue
        match = re.search(r"-?\d+", value)
        if match:
            return int(match.group())
    return None


def _parse_reset(value: str | None, now: datetime) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    try:
        numeric = float(raw)
        if numeric > 10_000_000_000:
            numeric /= 1000
        if numeric > now.timestamp() - 86_400:
            return datetime.fromtimestamp(numeric, UTC)
        return now + timedelta(seconds=max(0, numeric))
    except ValueError:
        pass
    duration = re.fullmatch(r"(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", raw)
    if duration and any(duration.groups()):
        seconds = int(duration.group(1) or 0) * 60 + float(duration.group(2) or 0)
        return now + timedelta(seconds=seconds)
    try:
        parsed = parsedate_to_datetime(raw)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError, OverflowError):
        return None


class ProviderReliabilityStore:
    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        base_cooldown_seconds: float = 30,
        max_cooldown_seconds: float = 900,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.base_cooldown_seconds = base_cooldown_seconds
        self.max_cooldown_seconds = max_cooldown_seconds

    async def available(
        self,
        session: AsyncSession,
        candidate: ProviderCandidate,
        *,
        now: datetime | None = None,
    ) -> bool:
        current = now or datetime.now(UTC)
        health = await self._get_health(session, candidate)
        if health is None:
            return True
        if health.state == HealthState.DISABLED.value:
            return False
        if health.state == HealthState.COOLDOWN.value:
            cooldown = _aware(health.cooldown_until)
            if cooldown is None or cooldown > current:
                return False
            health.state = HealthState.DEGRADED.value
            health.cooldown_until = None
        return True

    async def quota(
        self, session: AsyncSession, candidate: ProviderCandidate
    ) -> QuotaSnapshot | None:
        record = await session.scalar(
            select(ProviderQuotaSnapshot)
            .where(
                ProviderQuotaSnapshot.provider == candidate.provider,
                ProviderQuotaSnapshot.model == candidate.model,
            )
            .order_by(ProviderQuotaSnapshot.updated_at.desc())
            .limit(1)
        )
        if record is None:
            return None
        return QuotaSnapshot(
            requests_remaining=record.requests_remaining,
            tokens_remaining=record.tokens_remaining,
            reset_at=_aware(record.reset_at),
            source=record.source,
        )

    async def success(
        self,
        session: AsyncSession,
        candidate: ProviderCandidate,
        response: ModelResponse,
        *,
        project_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        prompt_version: str,
        latency_seconds: float,
    ) -> None:
        health = await self._health_for_update(session, candidate)
        health.state = HealthState.HEALTHY.value
        health.consecutive_failures = 0
        health.cooldown_until = None
        health.last_error = None
        await self._record_quota(
            session,
            candidate,
            quota_from_headers(response.response_headers),
            tokens_used=response.usage.total_tokens,
        )
        session.add(
            ModelUsageRecord(
                project_id=project_id,
                task_id=task_id,
                provider=candidate.provider,
                model=candidate.model,
                prompt_version=prompt_version,
                status="COMPLETED",
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                latency_seconds=latency_seconds,
            )
        )
        await session.flush()

    async def failure(
        self,
        session: AsyncSession,
        candidate: ProviderCandidate,
        error: ProviderError,
        *,
        project_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        prompt_version: str,
        latency_seconds: float,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(UTC)
        health = await self._health_for_update(session, candidate)
        health.consecutive_failures += 1
        health.last_error = Redactor().text(str(error))[-2000:]
        if error.status_code in {401, 403} or not error.retryable:
            health.state = HealthState.DISABLED.value
            health.cooldown_until = None
        elif isinstance(error, RateLimitError):
            health.state = HealthState.COOLDOWN.value
            delay = error.retry_after_seconds or self.base_cooldown_seconds
            health.cooldown_until = current + timedelta(seconds=max(1, delay))
        elif health.consecutive_failures >= self.failure_threshold:
            exponent = health.consecutive_failures - self.failure_threshold
            delay = min(self.max_cooldown_seconds, self.base_cooldown_seconds * (2**exponent))
            health.state = HealthState.COOLDOWN.value
            health.cooldown_until = current + timedelta(seconds=delay)
        else:
            health.state = HealthState.DEGRADED.value
        if error.response_headers:
            await self._record_quota(
                session,
                candidate,
                quota_from_headers(error.response_headers, now=current),
                tokens_used=0,
            )
        session.add(
            ModelUsageRecord(
                project_id=project_id,
                task_id=task_id,
                provider=candidate.provider,
                model=candidate.model,
                prompt_version=prompt_version,
                status="FAILED",
                latency_seconds=latency_seconds,
                error=health.last_error,
            )
        )
        await session.flush()

    async def _record_quota(
        self,
        session: AsyncSession,
        candidate: ProviderCandidate,
        snapshot: QuotaSnapshot,
        *,
        tokens_used: int,
    ) -> None:
        record = await session.scalar(
            select(ProviderQuotaSnapshot).where(
                ProviderQuotaSnapshot.provider == candidate.provider,
                ProviderQuotaSnapshot.model == candidate.model,
                ProviderQuotaSnapshot.window == "rolling",
            )
        )
        if record is None:
            record = ProviderQuotaSnapshot(
                provider=candidate.provider,
                model=candidate.model,
                window="rolling",
                requests_used=0,
                tokens_used=0,
                source="estimated",
            )
            session.add(record)
        record.requests_used += 1
        record.tokens_used += tokens_used
        if snapshot.requests_remaining is not None:
            record.requests_remaining = snapshot.requests_remaining
        if snapshot.tokens_remaining is not None:
            record.tokens_remaining = snapshot.tokens_remaining
        if snapshot.reset_at is not None:
            record.reset_at = snapshot.reset_at
        record.source = snapshot.source

    async def _get_health(
        self, session: AsyncSession, candidate: ProviderCandidate
    ) -> ModelHealthRecord | None:
        health: ModelHealthRecord | None = await session.scalar(
            select(ModelHealthRecord).where(
                ModelHealthRecord.provider == candidate.provider,
                ModelHealthRecord.model == candidate.model,
            )
        )
        return health

    async def _health_for_update(
        self, session: AsyncSession, candidate: ProviderCandidate
    ) -> ModelHealthRecord:
        health = await self._get_health(session, candidate)
        if health is None:
            health = ModelHealthRecord(
                provider=candidate.provider,
                model=candidate.model,
                state=HealthState.HEALTHY.value,
                consecutive_failures=0,
            )
            session.add(health)
        return health


class ReliableProviderGateway:
    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        store: ProviderReliabilityStore | None = None,
        quota_policy: QuotaPolicy | None = None,
    ) -> None:
        self.registry = registry
        self.store = store or ProviderReliabilityStore()
        self.quota_policy = quota_policy or QuotaPolicy(
            allow_paid_models=False, max_cloud_cost_usd_day=0
        )

    async def complete(
        self,
        session: AsyncSession,
        request: ModelRequest,
        candidates: list[ProviderCandidate],
        *,
        project_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        prompt_version: str = "unknown",
    ) -> ModelResponse:
        failures: list[str] = []
        for candidate in candidates:
            if not await self.store.available(session, candidate):
                failures.append(f"{candidate.provider}/{candidate.model}: circuit unavailable")
                continue
            quota = await self.store.quota(session, candidate)
            if not self.quota_policy.allows(candidate.billing_mode, quota):
                failures.append(f"{candidate.provider}/{candidate.model}: quota or budget blocked")
                continue
            provider = self.registry.get(candidate.provider)
            started = time.monotonic()
            model_request = request.model_copy(update={"model": candidate.model})
            try:
                response = await provider.complete(model_request)
            except ProviderError as error:
                await self.store.failure(
                    session,
                    candidate,
                    error,
                    project_id=project_id,
                    task_id=task_id,
                    prompt_version=prompt_version,
                    latency_seconds=time.monotonic() - started,
                )
                failures.append(f"{candidate.provider}/{candidate.model}: {type(error).__name__}")
                continue
            await self.store.success(
                session,
                candidate,
                response,
                project_id=project_id,
                task_id=task_id,
                prompt_version=prompt_version,
                latency_seconds=time.monotonic() - started,
            )
            return response
        detail = "; ".join(failures) if failures else "no candidates"
        raise AllProvidersUnavailable(f"all provider candidates failed or were blocked: {detail}")


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)

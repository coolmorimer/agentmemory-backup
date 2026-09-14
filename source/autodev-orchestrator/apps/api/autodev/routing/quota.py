from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from autodev.routing.models import BillingMode


@dataclass(frozen=True, slots=True)
class QuotaSnapshot:
    requests_remaining: int | None = None
    tokens_remaining: int | None = None
    reset_at: datetime | None = None
    source: str = "unknown"


class QuotaPolicy:
    def __init__(self, *, allow_paid_models: bool, max_cloud_cost_usd_day: float) -> None:
        self.allow_paid_models = allow_paid_models
        self.max_cloud_cost_usd_day = max_cloud_cost_usd_day

    def allows(self, billing_mode: BillingMode, snapshot: QuotaSnapshot | None) -> bool:
        if billing_mode is BillingMode.PAID:
            return self.allow_paid_models and self.max_cloud_cost_usd_day > 0
        if snapshot is None:
            return True
        if snapshot.requests_remaining is not None and snapshot.requests_remaining <= 0:
            return False
        return not (snapshot.tokens_remaining is not None and snapshot.tokens_remaining <= 0)

    @staticmethod
    def score(snapshot: QuotaSnapshot | None) -> float:
        if snapshot is None:
            return 0.5
        values = [
            value
            for value in (snapshot.requests_remaining, snapshot.tokens_remaining)
            if value is not None
        ]
        if not values:
            return 0.5
        if min(values) <= 0:
            return 0.0
        return min(1.0, min(values) / 100)

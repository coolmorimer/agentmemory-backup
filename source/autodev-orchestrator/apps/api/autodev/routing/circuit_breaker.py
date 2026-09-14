from __future__ import annotations

import random
import time
from dataclasses import dataclass

from autodev.routing.models import HealthState


@dataclass(slots=True)
class CircuitSnapshot:
    state: HealthState = HealthState.HEALTHY
    consecutive_failures: int = 0
    cooldown_until: float | None = None


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        base_cooldown_seconds: float = 30,
        max_cooldown_seconds: float = 900,
        jitter_ratio: float = 0.2,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.base_cooldown_seconds = base_cooldown_seconds
        self.max_cooldown_seconds = max_cooldown_seconds
        self.jitter_ratio = jitter_ratio
        self.snapshot = CircuitSnapshot()

    def available(self, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        if self.snapshot.state is HealthState.DISABLED:
            return False
        if self.snapshot.state is HealthState.COOLDOWN:
            if self.snapshot.cooldown_until is not None and current >= self.snapshot.cooldown_until:
                self.snapshot.state = HealthState.DEGRADED
                self.snapshot.cooldown_until = None
                return True
            return False
        return True

    def success(self) -> None:
        self.snapshot = CircuitSnapshot()

    def failure(self, *, now: float | None = None, permanent: bool = False) -> None:
        if permanent:
            self.snapshot.state = HealthState.DISABLED
            self.snapshot.cooldown_until = None
            return
        current = time.monotonic() if now is None else now
        self.snapshot.consecutive_failures += 1
        if self.snapshot.consecutive_failures < self.failure_threshold:
            self.snapshot.state = HealthState.DEGRADED
            return
        exponent = self.snapshot.consecutive_failures - self.failure_threshold
        base = min(self.max_cooldown_seconds, self.base_cooldown_seconds * (2**exponent))
        jitter = random.uniform(0, base * self.jitter_ratio)
        self.snapshot.state = HealthState.COOLDOWN
        self.snapshot.cooldown_until = current + base + jitter

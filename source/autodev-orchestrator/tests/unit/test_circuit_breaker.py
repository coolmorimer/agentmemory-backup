from autodev.routing.circuit_breaker import CircuitBreaker
from autodev.routing.models import HealthState


def test_repeated_failures_open_circuit_then_half_open_after_cooldown() -> None:
    breaker = CircuitBreaker(failure_threshold=2, base_cooldown_seconds=10, jitter_ratio=0)

    breaker.failure(now=100)
    assert breaker.snapshot.state is HealthState.DEGRADED
    breaker.failure(now=100)
    assert breaker.snapshot.state is HealthState.COOLDOWN
    assert breaker.available(now=109) is False
    assert breaker.available(now=110) is True
    assert breaker.snapshot.state is HealthState.DEGRADED

    breaker.success()
    assert breaker.snapshot.state is HealthState.HEALTHY


def test_permanent_failure_disables_provider() -> None:
    breaker = CircuitBreaker()

    breaker.failure(permanent=True)

    assert breaker.snapshot.state is HealthState.DISABLED
    assert breaker.available() is False

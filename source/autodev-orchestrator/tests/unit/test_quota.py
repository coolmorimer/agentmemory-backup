from autodev.routing.models import BillingMode
from autodev.routing.quota import QuotaPolicy, QuotaSnapshot


def test_unknown_quota_is_not_scored_as_infinite() -> None:
    assert QuotaPolicy.score(None) == 0.5
    assert QuotaPolicy.score(QuotaSnapshot()) == 0.5


def test_exhausted_quota_is_blocked() -> None:
    policy = QuotaPolicy(allow_paid_models=False, max_cloud_cost_usd_day=0)

    assert policy.allows(BillingMode.FREE, QuotaSnapshot(requests_remaining=0)) is False
    assert policy.allows(BillingMode.FREE, QuotaSnapshot(tokens_remaining=0)) is False


def test_paid_models_require_explicit_permission_and_budget() -> None:
    assert (
        QuotaPolicy(allow_paid_models=False, max_cloud_cost_usd_day=10).allows(
            BillingMode.PAID, None
        )
        is False
    )
    assert (
        QuotaPolicy(allow_paid_models=True, max_cloud_cost_usd_day=0).allows(BillingMode.PAID, None)
        is False
    )
    assert (
        QuotaPolicy(allow_paid_models=True, max_cloud_cost_usd_day=10).allows(
            BillingMode.PAID, None
        )
        is True
    )

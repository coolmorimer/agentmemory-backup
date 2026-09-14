from autodev.config import Settings


def test_paid_models_are_disabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.allow_paid_models is False
    assert settings.max_cloud_cost_usd_day == 0
    assert settings.max_cloud_cost_usd_month == 0

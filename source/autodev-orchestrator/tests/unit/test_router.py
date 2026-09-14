import pytest

from autodev.domain.enums import PrivacyLevel
from autodev.routing.models import BillingMode, ModelProfile, TaskRequirements
from autodev.routing.router import ModelRouter, NoEligibleModel, default_profiles


def test_tool_task_routes_to_codex_when_local_models_lack_tools() -> None:
    decision = ModelRouter(default_profiles()).route(
        TaskRequirements(
            task_type="implementation",
            complexity=0.7,
            privacy_level=PrivacyLevel.LOCAL_ONLY,
            requires_tools=True,
            requires_structured_output=True,
        )
    )

    assert decision.model_id == "codex/app-server"


def test_private_code_excludes_unknown_cloud_provider() -> None:
    cloud = ModelProfile(
        id="cloud/model",
        provider="cloud",
        billing_mode=BillingMode.FREE,
        local=False,
        accepts_private_code=False,
        capabilities={"structured_output"},
        quality=1,
    )

    with pytest.raises(NoEligibleModel):
        ModelRouter([cloud]).route(
            TaskRequirements(
                task_type="planning",
                complexity=0.8,
                privacy_level=PrivacyLevel.PRIVATE,
                requires_structured_output=True,
            )
        )


def test_paid_provider_requires_enabled_nonzero_budget() -> None:
    paid = ModelProfile(
        id="cloud/paid",
        provider="cloud",
        billing_mode=BillingMode.PAID,
        accepts_private_code=True,
        capabilities={"structured_output"},
        quality=1,
    )
    request = TaskRequirements(
        task_type="planning",
        complexity=0.8,
        privacy_level=PrivacyLevel.PUBLIC,
        requires_structured_output=True,
    )

    with pytest.raises(NoEligibleModel):
        ModelRouter([paid], allow_paid_models=False, max_cloud_cost_usd_day=10).route(request)
    with pytest.raises(NoEligibleModel):
        ModelRouter([paid], allow_paid_models=True, max_cloud_cost_usd_day=0).route(request)
    assert (
        ModelRouter([paid], allow_paid_models=True, max_cloud_cost_usd_day=10)
        .route(request)
        .model_id
        == "cloud/paid"
    )


def test_explicit_model_override_still_enforces_policy() -> None:
    request = TaskRequirements(
        task_type="implementation",
        complexity=0.5,
        privacy_level=PrivacyLevel.LOCAL_ONLY,
        requires_tools=True,
        requires_structured_output=True,
    )

    decision = ModelRouter(default_profiles()).route(request, preferred_model_id="codex/app-server")

    assert decision.model_id == "codex/app-server"
    assert "user_override" in decision.reasons

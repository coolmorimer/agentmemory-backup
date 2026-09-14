from __future__ import annotations

from dataclasses import dataclass

from autodev.domain.enums import PrivacyLevel
from autodev.routing.models import (
    BillingMode,
    HealthState,
    ModelProfile,
    RoutingDecision,
    TaskRequirements,
)


class NoEligibleModel(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RoutingWeights:
    quality: float = 0.30
    task_match: float = 0.25
    reliability: float = 0.15
    quota: float = 0.10
    latency: float = 0.10
    privacy: float = 0.10


class ModelRouter:
    def __init__(
        self,
        profiles: list[ModelProfile],
        *,
        allow_paid_models: bool = False,
        max_cloud_cost_usd_day: float = 0.0,
        weights: RoutingWeights | None = None,
    ) -> None:
        self._profiles = tuple(profiles)
        self._allow_paid_models = allow_paid_models
        self._max_cloud_cost_usd_day = max_cloud_cost_usd_day
        self._weights = weights or RoutingWeights()

    def route(
        self, request: TaskRequirements, *, preferred_model_id: str | None = None
    ) -> RoutingDecision:
        candidates: list[tuple[float, ModelProfile, list[str]]] = []
        for profile in self._profiles:
            if preferred_model_id is not None and profile.id != preferred_model_id:
                continue
            eligible, reasons = self._eligible(profile, request)
            if not eligible:
                continue
            score = self._score(profile, request)
            candidates.append((score, profile, reasons))
        if not candidates:
            selection = f" preferred model {preferred_model_id!r}" if preferred_model_id else ""
            raise NoEligibleModel(
                f"no{selection} satisfies health, privacy, budget, context, and capability policy"
            )
        score, profile, reasons = max(candidates, key=lambda item: item[0])
        return RoutingDecision(
            model_id=profile.id,
            provider=profile.provider,
            score=round(score, 6),
            reasons=[*reasons, *(["user_override"] if preferred_model_id else [])],
        )

    def _eligible(self, profile: ModelProfile, request: TaskRequirements) -> tuple[bool, list[str]]:
        if profile.health in {HealthState.COOLDOWN, HealthState.DISABLED}:
            return False, []
        if profile.billing_mode is BillingMode.PAID and (
            not self._allow_paid_models or self._max_cloud_cost_usd_day <= 0
        ):
            return False, []
        if request.privacy_level is PrivacyLevel.LOCAL_ONLY and not profile.local:
            return False, []
        if request.privacy_level is PrivacyLevel.PRIVATE and not (
            profile.local or profile.accepts_private_code
        ):
            return False, []
        if request.context_tokens_estimate > profile.max_context:
            return False, []
        required = set()
        if request.requires_tools:
            required.add("tools")
        if request.requires_vision:
            required.add("vision")
        if request.requires_structured_output:
            required.add("structured_output")
        if not required.issubset(profile.capabilities):
            return False, []
        return True, [
            f"health={profile.health.value}",
            f"billing={profile.billing_mode.value}",
            f"privacy={'local' if profile.local else 'allowed'}",
        ]

    def _score(self, profile: ModelProfile, request: TaskRequirements) -> float:
        task_match = profile.task_scores.get(request.task_type, profile.quality * 0.5)
        if profile.billing_mode is BillingMode.LOCAL:
            quota_score = 1.0
        elif profile.quota_remaining is None:
            quota_score = 0.5
        else:
            quota_score = min(1.0, profile.quota_remaining)
        latency_score = 1 / (1 + profile.expected_latency_seconds)
        privacy_score = 1.0 if profile.local else 0.75
        health_multiplier = 1.0 if profile.health is HealthState.HEALTHY else 0.5
        weights = self._weights
        raw = (
            profile.quality * weights.quality
            + task_match * weights.task_match
            + profile.reliability * weights.reliability
            + quota_score * weights.quota
            + latency_score * weights.latency
            + privacy_score * weights.privacy
        )
        complexity_fit = 1 - abs(profile.quality - request.complexity) * 0.1
        return raw * health_multiplier * complexity_fit


def default_profiles() -> list[ModelProfile]:
    return [
        ModelProfile(
            id="ollama/qwen2.5-coder:7b",
            provider="ollama",
            billing_mode=BillingMode.LOCAL,
            local=True,
            accepts_private_code=True,
            capabilities={"structured_output"},
            task_scores={"implementation": 0.72, "log_analysis": 0.82, "review": 0.70},
            quality=0.70,
            reliability=0.80,
            expected_latency_seconds=6,
            max_context=32_768,
        ),
        ModelProfile(
            id="ollama/qwen2.5-coder:14b",
            provider="ollama",
            billing_mode=BillingMode.LOCAL,
            local=True,
            accepts_private_code=True,
            capabilities={"structured_output"},
            task_scores={"implementation": 0.82, "review": 0.86},
            quality=0.82,
            reliability=0.82,
            expected_latency_seconds=12,
            max_context=16_384,
        ),
        ModelProfile(
            id="ollama/qwen3:14b",
            provider="ollama",
            billing_mode=BillingMode.LOCAL,
            local=True,
            accepts_private_code=True,
            capabilities={"structured_output"},
            task_scores={"planning": 0.90, "reasoning": 0.88},
            quality=0.86,
            reliability=0.80,
            expected_latency_seconds=14,
            max_context=16_384,
        ),
        ModelProfile(
            id="ollama/gemma3:12b",
            provider="ollama",
            billing_mode=BillingMode.LOCAL,
            local=True,
            accepts_private_code=True,
            capabilities={"vision", "structured_output"},
            task_scores={"vision": 0.90, "ui_qa": 0.88},
            quality=0.82,
            reliability=0.80,
            expected_latency_seconds=13,
            max_context=16_384,
        ),
        ModelProfile(
            id="ollama/deepseek-coder-v2:16b",
            provider="ollama",
            billing_mode=BillingMode.LOCAL,
            local=True,
            accepts_private_code=True,
            capabilities={"structured_output"},
            task_scores={"implementation": 0.84, "review": 0.87},
            quality=0.83,
            reliability=0.78,
            expected_latency_seconds=15,
            max_context=16_384,
        ),
        ModelProfile(
            id="ollama/qwen3-embedding:0.6b",
            provider="ollama",
            billing_mode=BillingMode.LOCAL,
            local=True,
            accepts_private_code=True,
            capabilities=set(),
            task_scores={"embedding": 0.84},
            quality=0.72,
            reliability=0.88,
            expected_latency_seconds=2,
            max_context=32_768,
        ),
        ModelProfile(
            id="ollama/qwen3-embedding:4b",
            provider="ollama",
            billing_mode=BillingMode.LOCAL,
            local=True,
            accepts_private_code=True,
            capabilities=set(),
            task_scores={"embedding": 0.92},
            quality=0.84,
            reliability=0.86,
            expected_latency_seconds=5,
            max_context=40_000,
        ),
        ModelProfile(
            id="codex/app-server",
            provider="codex",
            billing_mode=BillingMode.LOCAL,
            local=True,
            accepts_private_code=True,
            capabilities={"tools", "structured_output", "vision"},
            task_scores={"implementation": 0.98, "debugging": 0.98},
            quality=0.96,
            reliability=0.95,
            expected_latency_seconds=20,
            max_context=400_000,
        ),
    ]

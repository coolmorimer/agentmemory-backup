from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from autodev.domain.enums import PrivacyLevel


class BillingMode(StrEnum):
    LOCAL = "local"
    FREE = "free"
    PAID = "paid"


class HealthState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    COOLDOWN = "COOLDOWN"
    DISABLED = "DISABLED"


class TaskRequirements(BaseModel):
    task_type: str
    complexity: float = Field(ge=0, le=1)
    context_tokens_estimate: int = Field(default=0, ge=0)
    privacy_level: PrivacyLevel = PrivacyLevel.PRIVATE
    requires_tools: bool = False
    requires_vision: bool = False
    requires_structured_output: bool = False


class ModelProfile(BaseModel):
    id: str
    provider: str
    billing_mode: BillingMode
    local: bool = False
    accepts_private_code: bool = False
    capabilities: set[str] = Field(default_factory=set)
    task_scores: dict[str, float] = Field(default_factory=dict)
    quality: float = Field(ge=0, le=1)
    reliability: float = Field(default=1, ge=0, le=1)
    expected_latency_seconds: float = Field(default=1, gt=0)
    max_context: int = Field(default=16_384, gt=0)
    quota_remaining: float | None = Field(default=None, ge=0)
    health: HealthState = HealthState.HEALTHY


class RoutingDecision(BaseModel):
    model_id: str
    provider: str
    score: float
    reasons: list[str]

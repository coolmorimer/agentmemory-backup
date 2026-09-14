from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DeploymentEvidence(BaseModel):
    ci_green: bool = False
    staging_green: bool = False
    smoke_green: bool = False
    healthcheck_defined: bool = False
    rollback_configured: bool = False
    unresolved_high_findings: int = Field(default=0, ge=0)


class PolicyDecision(BaseModel):
    allowed: bool
    requires_approval: bool = False
    blockers: list[str] = Field(default_factory=list)


class DeploymentPolicy:
    def __init__(
        self,
        *,
        production_mode: Literal["auto", "require_approval", "disabled"] = "require_approval",
    ) -> None:
        self.production_mode = production_mode

    def evaluate(
        self,
        environment: Literal["staging", "production"],
        evidence: DeploymentEvidence,
        *,
        approval_granted: bool = False,
    ) -> PolicyDecision:
        if environment == "staging":
            blockers = [] if evidence.ci_green else ["CI is not green"]
            return PolicyDecision(allowed=not blockers, blockers=blockers)
        if self.production_mode == "disabled":
            return PolicyDecision(allowed=False, blockers=["production deployment is disabled"])
        checks = {
            "CI is not green": evidence.ci_green,
            "staging is not green": evidence.staging_green,
            "smoke tests are not green": evidence.smoke_green,
            "healthcheck is not defined": evidence.healthcheck_defined,
            "rollback is not configured": evidence.rollback_configured,
            "high severity findings remain open": evidence.unresolved_high_findings == 0,
        }
        blockers = [message for message, passed in checks.items() if not passed]
        if blockers:
            return PolicyDecision(allowed=False, blockers=blockers)
        requires_approval = self.production_mode == "require_approval" and not approval_granted
        return PolicyDecision(
            allowed=not requires_approval,
            requires_approval=requires_approval,
        )

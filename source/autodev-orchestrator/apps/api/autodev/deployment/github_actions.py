from __future__ import annotations

import asyncio
import os

import httpx

from autodev.deployment.base import (
    DeploymentError,
    DeploymentRequest,
    DeploymentResult,
    DeploymentVerification,
    VerificationCheck,
)


class GitHubActionsDeploymentAdapter:
    name = "github-actions"

    def __init__(
        self,
        repository: str,
        workflow: str,
        *,
        rollback_workflow: str | None = None,
        token_env: str = "GITHUB_TOKEN",
        api_url: str = "https://api.github.com",
        client: httpx.AsyncClient | None = None,
        poll_interval_seconds: float = 10,
        max_poll_attempts: int = 60,
    ) -> None:
        if repository.count("/") != 1:
            raise ValueError("GitHub repository must use owner/name format")
        self.repository = repository
        self.workflow = workflow
        self.rollback_workflow = rollback_workflow
        self.token_env = token_env
        self.api_url = api_url.rstrip("/")
        self.client = client
        self.poll_interval_seconds = poll_interval_seconds
        self.max_poll_attempts = max_poll_attempts

    async def deploy(self, request: DeploymentRequest) -> DeploymentResult:
        payload: dict[str, object] = {
            "ref": request.release_ref,
            "inputs": {
                "environment": request.environment,
                "release_ref": request.release_ref,
            },
        }
        response = await self._request(
            "POST",
            f"/repos/{self.repository}/actions/workflows/{self.workflow}/dispatches",
            json=payload,
        )
        body = response.json()
        run_id = body.get("workflow_run_id")
        if not run_id:
            raise DeploymentError("GitHub dispatch response did not include workflow_run_id")
        return DeploymentResult(
            external_id=str(run_id),
            release_ref=request.release_ref,
            previous_release_ref=_optional_string(request.metadata.get("previous_release_ref")),
            detail=str(body.get("html_url") or body.get("run_url") or ""),
        )

    async def verify(
        self, request: DeploymentRequest, deployment: DeploymentResult
    ) -> DeploymentVerification:
        del request
        body: dict[str, object] = {}
        for attempt in range(self.max_poll_attempts):
            response = await self._request(
                "GET", f"/repos/{self.repository}/actions/runs/{deployment.external_id}"
            )
            body = response.json()
            if body.get("status") == "completed":
                break
            if attempt + 1 < self.max_poll_attempts:
                await asyncio.sleep(self.poll_interval_seconds)
        status = str(body.get("status") or "unknown")
        conclusion = str(body.get("conclusion") or "pending")
        return DeploymentVerification(
            checks=[
                VerificationCheck(
                    name="github-actions-workflow",
                    passed=status == "completed" and conclusion == "success",
                    detail=f"status={status}; conclusion={conclusion}",
                    artifact_path=_optional_string(body.get("html_url")),
                )
            ]
        )

    async def rollback(
        self, request: DeploymentRequest, deployment: DeploymentResult
    ) -> DeploymentResult:
        if not self.rollback_workflow or not deployment.previous_release_ref:
            raise DeploymentError("GitHub Actions rollback workflow or previous release is missing")
        response = await self._request(
            "POST",
            f"/repos/{self.repository}/actions/workflows/{self.rollback_workflow}/dispatches",
            json={
                "ref": deployment.previous_release_ref,
                "inputs": {
                    "environment": request.environment,
                    "release_ref": deployment.previous_release_ref,
                },
            },
        )
        body = response.json()
        run_id = body.get("workflow_run_id")
        if not run_id:
            raise DeploymentError("GitHub rollback response did not include workflow_run_id")
        return DeploymentResult(
            external_id=str(run_id),
            release_ref=deployment.previous_release_ref,
            previous_release_ref=deployment.release_ref,
            detail=str(body.get("html_url") or ""),
        )

    async def collect_logs(self, request: DeploymentRequest, deployment: DeploymentResult) -> str:
        del request
        response = await self._request(
            "GET", f"/repos/{self.repository}/actions/runs/{deployment.external_id}"
        )
        return response.text[-16_000:]

    async def _request(
        self, method: str, path: str, *, json: dict[str, object] | None = None
    ) -> httpx.Response:
        token = os.getenv(self.token_env)
        if not token:
            raise DeploymentError(
                f"GitHub credential environment variable is not set: {self.token_env}"
            )
        headers = {
            "accept": "application/vnd.github+json",
            "authorization": f"Bearer {token}",
            "x-github-api-version": "2026-03-10",
        }
        client = self.client or httpx.AsyncClient(timeout=60)
        owns_client = self.client is None
        try:
            response = await client.request(
                method, f"{self.api_url}{path}", json=json, headers=headers
            )
            if response.status_code >= 400:
                raise DeploymentError(f"GitHub Actions API failed with HTTP {response.status_code}")
            return response
        except httpx.HTTPError as error:
            raise DeploymentError(
                f"GitHub Actions transport failed: {type(error).__name__}"
            ) from error
        finally:
            if owns_client:
                await client.aclose()


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None

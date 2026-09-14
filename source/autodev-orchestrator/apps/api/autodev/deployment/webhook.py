from __future__ import annotations

import os

import httpx

from autodev.deployment.base import (
    DeploymentError,
    DeploymentRequest,
    DeploymentResult,
    DeploymentVerification,
)


class WebhookDeploymentAdapter:
    name = "webhook"

    def __init__(
        self,
        base_url: str,
        *,
        secret_env: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.secret_env = secret_env
        self.client = client
        self.timeout_seconds = timeout_seconds

    async def deploy(self, request: DeploymentRequest) -> DeploymentResult:
        response = await self._post("/deploy", request.model_dump(mode="json"))
        payload = response.json()
        try:
            return DeploymentResult(
                external_id=str(payload["external_id"]),
                release_ref=str(payload.get("release_ref") or request.release_ref),
                previous_release_ref=payload.get("previous_release_ref"),
                detail=str(payload.get("detail") or ""),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise DeploymentError("deployment webhook returned an invalid result") from error

    async def verify(
        self, request: DeploymentRequest, deployment: DeploymentResult
    ) -> DeploymentVerification:
        response = await self._post(
            "/verify",
            {"request": request.model_dump(mode="json"), "deployment": deployment.model_dump()},
        )
        try:
            return DeploymentVerification.model_validate(response.json())
        except (ValueError, TypeError) as error:
            raise DeploymentError("verification webhook returned an invalid result") from error

    async def rollback(
        self, request: DeploymentRequest, deployment: DeploymentResult
    ) -> DeploymentResult:
        response = await self._post(
            "/rollback",
            {"request": request.model_dump(mode="json"), "deployment": deployment.model_dump()},
        )
        try:
            return DeploymentResult.model_validate(response.json())
        except (ValueError, TypeError) as error:
            raise DeploymentError("rollback webhook returned an invalid result") from error

    async def collect_logs(self, request: DeploymentRequest, deployment: DeploymentResult) -> str:
        response = await self._post(
            "/logs",
            {"request": request.model_dump(mode="json"), "deployment": deployment.model_dump()},
        )
        try:
            payload = response.json()
            return str(payload.get("logs") or "")
        except ValueError:
            return response.text

    async def _post(self, path: str, payload: dict[str, object]) -> httpx.Response:
        headers = {"content-type": "application/json"}
        if self.secret_env:
            secret = os.getenv(self.secret_env)
            if not secret:
                raise DeploymentError(
                    f"deployment credential environment variable is not set: {self.secret_env}"
                )
            headers["authorization"] = f"Bearer {secret}"
        client = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        owns_client = self.client is None
        try:
            response = await client.post(f"{self.base_url}{path}", json=payload, headers=headers)
            if response.status_code >= 400:
                raise DeploymentError(f"deployment webhook failed with HTTP {response.status_code}")
            return response
        except httpx.HTTPError as error:
            raise DeploymentError(
                f"deployment webhook transport failed: {type(error).__name__}"
            ) from error
        finally:
            if owns_client:
                await client.aclose()

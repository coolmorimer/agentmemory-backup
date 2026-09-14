# Deployment and rollback

Deployment providers implement `deploy`, `verify`, `rollback`, and log collection. Available adapters
cover controlled Docker Compose, GitHub Actions workflow dispatch/status, and generic signed webhooks.
The coordinator persists the deployment before executing an adapter.

Staging requires release evidence and verification. Production additionally requires green CI,
green staging/smoke, a health check, configured rollback, and the configured approval policy. A failed
verification collects redacted logs, executes the exact previous-release rollback, records checks and
an incident, and returns `ROLLED_BACK` or `ROLLBACK_FAILED`.

Real targets are never selected by tests. Set credentials only in the runtime environment, approve via
`/api/approvals/{id}/approve` (or the deployment-specific compatibility endpoint), and inspect
`/api/deployments` before and after release.

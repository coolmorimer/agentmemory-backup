# Adding a deployment adapter

Implement the `DeploymentProvider` protocol: `deploy`, `verify`, `rollback`, and `collect_logs`. Inputs
must identify the immutable release and the exact previous release. Use injected HTTP/command clients,
argv execution without a shell, finite polling, and redacted bounded output.

Add contract tests proving successful verification, missing prerequisite rejection, credential-safe
errors, deterministic rollback after a failed health check, and incident persistence. The adapter must
not weaken `DeploymentPolicy`; production approval and rollback configuration remain coordinator gates.

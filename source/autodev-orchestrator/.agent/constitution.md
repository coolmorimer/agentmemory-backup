# Project Constitution

- Python 3.13 is the target runtime.
- PostgreSQL is the source of truth for projects, tasks, attempts, checks, and deployments.
- Redis may hold only replaceable ephemeral state.
- Every public API and state transition requires tests, including failure paths.
- Every database schema change requires a versioned migration.
- Deterministic evidence, not an AI assertion, decides completion.
- Integrations must remain behind replaceable typed adapters.
- Secrets must never enter Git, prompts, model logs, audit metadata, or memory.
- Paid model use is disabled unless an explicit policy enables a non-zero budget.
- Production changes require CI/staging/health/rollback gates and configured approval policy.
- Tests and validations must not be weakened merely to make a build pass.
- Destructive commands and migrations require a policy decision and, by default, approval.


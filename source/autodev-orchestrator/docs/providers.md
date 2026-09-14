# Providers and routing

Provider defaults are read from `config/providers.yaml.example`; keys are never stored in YAML.
Runtime overrides live in PostgreSQL. API keys entered in the React dashboard or VS Code extension
are encrypted with `AUTODEV_CREDENTIAL_KEY`, are redacted from logs/audit events, and are exposed by
the API only as the boolean `credential_configured`. Run `scripts/bootstrap-secrets.ps1` once to
create the ignored local master key.

Supported adapters are Ollama and generic OpenAI-compatible APIs, which covers OpenRouter, LiteLLM
gateways, LM Studio, and named cloud endpoints. OpenRouter defaults to
`https://openrouter.ai/api/v1`; paid routing and private-code transmission remain independently
policy-gated.

Routing first removes ineligible candidates by health, cooldown, paid-budget policy, privacy,
context size, and required capabilities. It then scores quality, task fit, reliability, quota,
latency, privacy, and complexity fit. A user model override narrows selection but cannot bypass those
policies. HTTP 429 and transport timeouts update durable health/quota state and fall through to the
next candidate. Provider responses and errors are bounded before persistence.

Runtime configuration endpoints:

- `GET /api/providers` — safe provider configuration and credential presence;
- `PUT /api/providers/{name}` — enable/update a provider and optionally replace its key;
- `DELETE /api/providers/{name}/credential` — clear the encrypted key;
- `POST /api/providers/{name}/test` — authenticated provider health check;
- `POST /api/models/discover?provider=...` — refresh the persistent model catalog;
- `GET /api/model-selection` and `PUT /api/model-selection/{role}` — read/change role routing;
- `GET /api/models`, `/api/model-usage`, and `/api/dashboard/models` — catalog and evidence.

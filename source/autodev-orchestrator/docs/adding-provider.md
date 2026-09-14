# Adding a provider

1. Implement `LLMProvider` in `autodev.providers` using an injected HTTP client and bounded timeout.
2. Translate responses to `ModelResponse`; never return or persist credential-bearing headers.
3. Register the kind in `ProviderSettings` and `build_provider_registry`.
4. Add health, success, 429, timeout, malformed response, and cleanup tests.
5. Add model profiles with explicit billing, privacy, context, and capabilities.
6. Document required environment-variable names in the example catalog, never their values.
7. Prove the reliability gateway falls back and updates durable usage/health/quota state.

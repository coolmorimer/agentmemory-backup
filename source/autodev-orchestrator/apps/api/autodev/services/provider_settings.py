from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autodev.config import Settings
from autodev.db.models import ModelConfigRecord, ProviderConfigRecord, RoutingPreferenceRecord
from autodev.providers.base import LLMProvider
from autodev.providers.configuration import ProviderCatalog, ProviderSettings, load_provider_catalog
from autodev.providers.ollama import OllamaProvider
from autodev.providers.openai_compatible import OpenAICompatibleProvider
from autodev.routing.models import BillingMode, ModelProfile
from autodev.routing.router import ModelRouter, default_profiles


class ProviderSettingsError(RuntimeError):
    pass


@dataclass(slots=True)
class EffectiveProvider:
    name: str
    kind: str
    enabled: bool
    base_url: str
    api_key_env: str | None
    billing_mode: str
    accepts_private_code: bool
    timeout_seconds: float
    encrypted_api_key: str | None = None


class CredentialVault:
    def __init__(self, key: SecretStr | None) -> None:
        raw = key.get_secret_value().strip() if key else ""
        try:
            self._fernet = Fernet(raw.encode("ascii")) if raw else None
        except (ValueError, UnicodeEncodeError) as error:
            raise ProviderSettingsError("AUTODEV_CREDENTIAL_KEY is invalid") from error

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def encrypt(self, value: SecretStr) -> str:
        if self._fernet is None:
            raise ProviderSettingsError(
                "credential vault is not configured; set AUTODEV_CREDENTIAL_KEY"
            )
        return self._fernet.encrypt(value.get_secret_value().encode("utf-8")).decode("ascii")

    def decrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        if self._fernet is None:
            raise ProviderSettingsError("credential vault is unavailable")
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as error:
            raise ProviderSettingsError("stored provider credential cannot be decrypted") from error


class ProviderSettingsService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.vault = CredentialVault(settings.credential_key)

    def _catalog(self) -> ProviderCatalog:
        candidates = (
            self.settings.project_root / "config" / "providers.yaml",
            self.settings.project_root / "config" / "providers.yaml.example",
            Path("config/providers.yaml"),
            Path("config/providers.yaml.example"),
        )
        for path in candidates:
            if path.is_file():
                catalog = load_provider_catalog(path)
                break
        else:
            catalog = ProviderCatalog(providers={})
        providers = dict(catalog.providers)
        providers["ollama"] = providers.get("ollama", ProviderSettings(kind="ollama")).model_copy(
            update={"base_url": self.settings.ollama_base_url}
        )
        providers["litellm"] = providers.get("litellm", ProviderSettings()).model_copy(
            update={"base_url": self.settings.litellm_base_url}
        )
        providers["openrouter"] = providers.get(
            "openrouter",
            ProviderSettings(api_key_env="OPENROUTER_API_KEY", billing_mode="free"),
        ).model_copy(update={"base_url": "https://openrouter.ai/api/v1"})
        return ProviderCatalog(providers=providers)

    async def effective(self, session: AsyncSession) -> dict[str, EffectiveProvider]:
        result = {
            name: EffectiveProvider(
                name=name,
                kind=item.kind,
                enabled=item.enabled,
                base_url=item.base_url or "",
                api_key_env=item.api_key_env,
                billing_mode=item.billing_mode,
                accepts_private_code=item.accepts_private_code,
                timeout_seconds=item.timeout_seconds,
            )
            for name, item in self._catalog().providers.items()
        }
        result["codex"] = EffectiveProvider(
            name="codex",
            kind="codex_app_server",
            enabled=True,
            base_url="local-process",
            api_key_env=None,
            billing_mode="local",
            accepts_private_code=True,
            timeout_seconds=600,
        )
        records = list(await session.scalars(select(ProviderConfigRecord)))
        for record in records:
            result[record.name] = EffectiveProvider(
                name=record.name,
                kind=record.kind,
                enabled=record.enabled,
                base_url=record.base_url,
                api_key_env=record.api_key_env,
                billing_mode=record.billing_mode,
                accepts_private_code=record.accepts_private_code,
                timeout_seconds=record.timeout_seconds,
                encrypted_api_key=record.encrypted_api_key,
            )
        return result

    async def public_configs(self, session: AsyncSession) -> list[dict[str, object]]:
        configs = await self.effective(session)
        output = []
        for config in sorted(configs.values(), key=lambda item: (not item.enabled, item.name)):
            data = asdict(config)
            data.pop("encrypted_api_key")
            data["credential_configured"] = bool(
                config.encrypted_api_key
                or (config.api_key_env and os.getenv(config.api_key_env))
            )
            data["vault_available"] = self.vault.available
            output.append(data)
        return output

    async def save(
        self,
        session: AsyncSession,
        *,
        name: str,
        kind: str,
        enabled: bool,
        base_url: str,
        api_key_env: str | None,
        api_key: SecretStr | None,
        billing_mode: str,
        accepts_private_code: bool,
        timeout_seconds: float,
    ) -> ProviderConfigRecord:
        record = await session.scalar(
            select(ProviderConfigRecord).where(ProviderConfigRecord.name == name)
        )
        if record is None:
            record = ProviderConfigRecord(
                name=name,
                kind=kind,
                enabled=enabled,
                base_url=base_url,
                billing_mode=billing_mode,
                accepts_private_code=accepts_private_code,
                timeout_seconds=timeout_seconds,
            )
            session.add(record)
        record.kind = kind
        record.enabled = enabled
        record.base_url = base_url.rstrip("/")
        record.api_key_env = api_key_env
        record.billing_mode = billing_mode
        record.accepts_private_code = accepts_private_code
        record.timeout_seconds = timeout_seconds
        if api_key is not None:
            record.encrypted_api_key = self.vault.encrypt(api_key)
        await session.flush()
        return record

    async def clear_credential(self, session: AsyncSession, name: str) -> bool:
        record = await session.scalar(
            select(ProviderConfigRecord).where(ProviderConfigRecord.name == name)
        )
        if record is None or record.encrypted_api_key is None:
            return False
        record.encrypted_api_key = None
        await session.flush()
        return True

    async def provider(self, session: AsyncSession, name: str) -> LLMProvider:
        config = (await self.effective(session)).get(name)
        if config is None:
            raise LookupError(f"unknown provider: {name}")
        if not config.enabled:
            raise ProviderSettingsError(f"provider is disabled: {name}")
        if not config.base_url:
            raise ProviderSettingsError(f"provider has no base URL: {name}")
        if config.kind == "ollama":
            return OllamaProvider(config.base_url, timeout_seconds=config.timeout_seconds)
        if config.kind == "openai_compatible":
            return OpenAICompatibleProvider(
                name=name,
                base_url=config.base_url,
                api_key_env=config.api_key_env,
                api_key=self.vault.decrypt(config.encrypted_api_key),
                timeout_seconds=config.timeout_seconds,
            )
        raise ProviderSettingsError(f"provider kind cannot be called through HTTP: {config.kind}")


class ModelSettingsService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.providers = ProviderSettingsService(settings)

    async def discover(self, session: AsyncSession, provider_name: str) -> list[str]:
        provider = await self.providers.provider(session, provider_name)
        if isinstance(provider, OllamaProvider | OpenAICompatibleProvider):
            names = sorted(await provider.list_models())
        else:
            raise ProviderSettingsError(f"model discovery is unsupported: {provider_name}")
        known_profiles = {profile.id: profile for profile in default_profiles()}
        existing = {
            item.model_id: item
            for item in await session.scalars(
                select(ModelConfigRecord).where(ModelConfigRecord.provider == provider_name)
            )
        }
        discovered_ids = []
        for remote_name in names:
            model_id = f"{provider_name}/{remote_name}"
            discovered_ids.append(model_id)
            record = existing.get(model_id)
            profile = known_profiles.get(model_id)
            roles = sorted(profile.task_scores) if profile else [
                "implementation",
                "review",
                "planning",
            ]
            capabilities = sorted(profile.capabilities) if profile else ["structured_output"]
            if record is None:
                local = provider_name in {"ollama", "lmstudio"}
                record = ModelConfigRecord(
                    model_id=model_id,
                    provider=provider_name,
                    display_name=remote_name,
                    enabled=True,
                    local=local,
                    installed=local,
                    capabilities=capabilities,
                    roles=roles,
                    max_context=profile.max_context if profile else 16_384,
                    quality=profile.quality if profile else 0.75,
                    reliability=profile.reliability if profile else 0.8,
                    expected_latency_seconds=(
                        profile.expected_latency_seconds if profile else (10 if local else 5)
                    ),
                )
                session.add(record)
            else:
                record.installed = provider_name in {"ollama", "lmstudio"}
                if profile:
                    record.capabilities = capabilities
                    record.roles = roles
                    record.max_context = profile.max_context
                    record.quality = profile.quality
                    record.reliability = profile.reliability
                    record.expected_latency_seconds = profile.expected_latency_seconds
        if provider_name in {"ollama", "lmstudio"}:
            for model_id, record in existing.items():
                if model_id not in discovered_ids:
                    record.installed = False
        await session.flush()
        return discovered_ids

    async def list_models(self, session: AsyncSession) -> list[dict[str, object]]:
        configs = await self.providers.effective(session)
        preferences = {
            item.role: item.model_id
            for item in await session.scalars(select(RoutingPreferenceRecord))
        }
        records = {item.model_id: item for item in await session.scalars(select(ModelConfigRecord))}
        models: dict[str, dict[str, object]] = {}
        for profile in default_profiles():
            provider = configs.get(profile.provider)
            record = records.get(profile.id)
            models[profile.id] = {
                **profile.model_dump(mode="json"),
                "display_name": profile.id.split("/", 1)[-1],
                "enabled": record.enabled if record else bool(provider and provider.enabled),
                "installed": record.installed if record else profile.provider == "codex",
                "roles": record.roles if record else sorted(profile.task_scores),
                "selected_for": sorted(
                    role for role, model_id in preferences.items() if model_id == profile.id
                ),
            }
        for record in records.values():
            if record.model_id in models:
                continue
            config = configs.get(record.provider)
            models[record.model_id] = {
                "id": record.model_id,
                "provider": record.provider,
                "billing_mode": self._billing_mode(config).value,
                "local": record.local,
                "accepts_private_code": bool(config and config.accepts_private_code),
                "capabilities": record.capabilities,
                "task_scores": {role: record.quality for role in record.roles},
                "quality": record.quality,
                "reliability": record.reliability,
                "expected_latency_seconds": record.expected_latency_seconds,
                "max_context": record.max_context,
                "quota_remaining": None,
                "health": "HEALTHY",
                "display_name": record.display_name,
                "enabled": record.enabled and bool(config and config.enabled),
                "installed": record.installed,
                "roles": record.roles,
                "selected_for": sorted(
                    role for role, model_id in preferences.items() if model_id == record.model_id
                ),
            }
        return sorted(models.values(), key=lambda item: (str(item["provider"]), str(item["id"])))

    async def set_preference(
        self, session: AsyncSession, *, role: str, model_id: str
    ) -> RoutingPreferenceRecord:
        models = {str(item["id"]): item for item in await self.list_models(session)}
        selected = models.get(model_id)
        if selected is None:
            raise LookupError(f"unknown model: {model_id}")
        if not selected["enabled"]:
            raise ProviderSettingsError(f"model or provider is disabled: {model_id}")
        if selected["local"] and not selected["installed"]:
            raise ProviderSettingsError(f"local model is not installed: {model_id}")
        roles = selected.get("roles")
        if not isinstance(roles, list) or role not in roles:
            raise ProviderSettingsError(f"model {model_id} is not configured for role {role}")
        preference = await session.get(RoutingPreferenceRecord, role)
        if preference is None:
            preference = RoutingPreferenceRecord(role=role, model_id=model_id)
            session.add(preference)
        else:
            preference.model_id = model_id
        await session.flush()
        return preference

    async def preferred(self, session: AsyncSession, role: str) -> str | None:
        preference = await session.get(RoutingPreferenceRecord, role)
        return preference.model_id if preference else None

    async def router(self, session: AsyncSession) -> ModelRouter:
        items = await self.list_models(session)
        profiles = [
            ModelProfile.model_validate(
                {key: value for key, value in item.items() if key in ModelProfile.model_fields}
            )
            for item in items
            if item["enabled"] and (not item["local"] or item["installed"])
        ]
        return ModelRouter(
            profiles,
            allow_paid_models=self.settings.allow_paid_models,
            max_cloud_cost_usd_day=self.settings.max_cloud_cost_usd_day,
        )

    @staticmethod
    def _billing_mode(config: EffectiveProvider | None) -> BillingMode:
        if config is None or config.billing_mode == "free" or config.billing_mode == "gateway":
            return BillingMode.FREE
        if config.billing_mode == "local":
            return BillingMode.LOCAL
        return BillingMode.PAID

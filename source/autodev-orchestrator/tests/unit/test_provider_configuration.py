from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from autodev.providers.configuration import (
    ProviderCatalog,
    ProviderConfigurationError,
    ProviderSettings,
    build_provider_registry,
    load_provider_catalog,
)
from autodev.services.provider_settings import CredentialVault, ProviderSettingsError


def test_example_catalog_registers_enabled_local_adapters() -> None:
    catalog = load_provider_catalog(Path("config/providers.yaml.example"))
    registry = build_provider_registry(catalog)

    assert registry.names() == ["litellm", "ollama"]


def test_enabled_provider_requires_explicit_endpoint() -> None:
    catalog = ProviderCatalog(
        providers={"generic": ProviderSettings(enabled=True, kind="openai_compatible")}
    )

    with pytest.raises(ProviderConfigurationError, match="no base_url"):
        build_provider_registry(catalog)


def test_plaintext_secret_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "providers.yaml"
    path.write_text(
        "providers:\n  unsafe:\n    enabled: true\n    api_key: do-not-accept\n",
        encoding="utf-8",
    )

    with pytest.raises(ProviderConfigurationError, match="api_key"):
        load_provider_catalog(path)


def test_credential_vault_encrypts_and_decrypts_without_plaintext_storage() -> None:
    vault = CredentialVault(SecretStr(Fernet.generate_key().decode("ascii")))

    encrypted = vault.encrypt(SecretStr("provider-secret"))

    assert encrypted != "provider-secret"
    assert vault.decrypt(encrypted) == "provider-secret"


def test_credential_vault_rejects_secret_when_master_key_is_missing() -> None:
    with pytest.raises(ProviderSettingsError, match="AUTODEV_CREDENTIAL_KEY"):
        CredentialVault(None).encrypt(SecretStr("provider-secret"))

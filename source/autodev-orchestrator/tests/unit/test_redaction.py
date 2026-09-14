from autodev.security.redaction import Redactor


def test_redacts_explicit_values_and_common_credentials() -> None:
    redactor = Redactor(["private-value"])
    source = (
        "Authorization: Bearer abcdefghijklmnop "
        "api_key=secret-key token: token-value value=private-value sk-abcdefghijklmnop"
    )

    result = redactor.text(source)

    assert "private-value" not in result
    assert "abcdefghijklmnop" not in result
    assert "secret-key" not in result
    assert "token-value" not in result
    assert result.count("[REDACTED]") >= 4


def test_redacts_nested_sensitive_fields_without_touching_safe_values() -> None:
    result = Redactor().data(
        {
            "headers": {"Authorization": "Bearer value"},
            "api_key": "value",
            "nested": [{"password": "value", "name": "visible"}],
        }
    )

    assert result == {
        "headers": {"Authorization": "[REDACTED]"},
        "api_key": "[REDACTED]",
        "nested": [{"password": "[REDACTED]", "name": "visible"}],
    }

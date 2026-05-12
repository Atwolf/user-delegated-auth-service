from __future__ import annotations

from observability.redaction import REDACTED, is_sensitive_key, redact_sensitive


def test_redaction_catches_nested_sensitive_keys() -> None:
    payload = {
        "safe": "visible",
        "headers": {
            "Authorization": "Bearer raw-header-token",
            "X-API-Key": "raw-api-key",
        },
        "nested": {
            "access_token": "raw-access-token",
            "AUTH0_MANAGEMENT_CLIENT_SECRET": "raw-management-secret",
            "clientSecret": "raw-client-secret",
            "items": [
                {"password": "raw-password", "safe_value": "kept"},
                {"metadata": {"private-key": "raw-private-key"}},
            ],
        },
    }

    redacted = redact_sensitive(payload)

    assert redacted["safe"] == "visible"
    assert redacted["headers"]["Authorization"] == REDACTED
    assert redacted["headers"]["X-API-Key"] == REDACTED
    assert redacted["nested"]["access_token"] == REDACTED
    assert redacted["nested"]["AUTH0_MANAGEMENT_CLIENT_SECRET"] == REDACTED
    assert redacted["nested"]["clientSecret"] == REDACTED
    assert redacted["nested"]["items"][0]["password"] == REDACTED
    assert redacted["nested"]["items"][0]["safe_value"] == "kept"
    assert redacted["nested"]["items"][1]["metadata"]["private-key"] == REDACTED


def test_redaction_catches_token_like_fields_and_inline_tokens() -> None:
    payload = {
        "accessToken": "raw-access-token",
        "refresh-token": "raw-refresh-token",
        "bearer_token": "raw-bearer-token",
        "message": (
            "called with access_token=raw-access-token and "
            "Authorization: Bearer raw-header-token and "
            "authorization smoke-secret-token"
        ),
    }

    redacted = redact_sensitive(payload)

    assert is_sensitive_key("accessToken")
    assert is_sensitive_key("refresh-token")
    assert is_sensitive_key("bearer_token")
    assert redacted["accessToken"] == REDACTED
    assert redacted["refresh-token"] == REDACTED
    assert redacted["bearer_token"] == REDACTED
    assert "raw-access-token" not in redacted["message"]
    assert "raw-header-token" not in redacted["message"]
    assert "smoke-secret-token" not in redacted["message"]
    assert "access_token=" + REDACTED in redacted["message"]
    assert "Bearer " + REDACTED in redacted["message"]
    assert "authorization " + REDACTED in redacted["message"]

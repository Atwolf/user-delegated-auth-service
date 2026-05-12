from __future__ import annotations

import base64
import hmac
import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

SESSION_CONTEXT_HEADER = "x-magnum-session-context"
SESSION_CONTEXT_SIGNATURE_HEADER = "x-magnum-session-signature"


class InternalAuthError(ValueError):
    """Raised when an internal service session context cannot be trusted."""


class TrustedSessionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    tenant_id: str | None = Field(default=None, min_length=1)
    token_ref: str | None = Field(default=None, min_length=1)
    token_scopes: list[str] = Field(default_factory=list)
    allowed_tools: list[str] | None = None
    correlation_id: str = Field(..., min_length=1)
    expires_at: datetime

    @field_validator("token_scopes")
    @classmethod
    def _normalize_token_scopes(cls, value: list[str]) -> list[str]:
        if any(scope == "" for scope in value):
            raise ValueError("token scopes must be non-empty strings")
        return sorted(set(value))

    @field_validator("allowed_tools")
    @classmethod
    def _normalize_allowed_tools(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if any(tool == "" for tool in value):
            raise ValueError("allowed tools must be non-empty strings")
        return sorted(set(value))

    @field_validator("expires_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        return value


def signed_session_context_headers(
    context: TrustedSessionContext,
    *,
    secret: str,
) -> dict[str, str]:
    encoded = encode_session_context(context)
    signature = sign_session_context(encoded, secret=secret)
    return {
        SESSION_CONTEXT_HEADER: encoded,
        SESSION_CONTEXT_SIGNATURE_HEADER: signature,
    }


def encode_session_context(context: TrustedSessionContext) -> str:
    payload = context.model_dump(mode="json")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def sign_session_context(encoded_context: str, *, secret: str) -> str:
    if not secret:
        raise InternalAuthError("internal auth secret is required")
    return hmac.new(
        secret.encode("utf-8"),
        encoded_context.encode("ascii"),
        sha256,
    ).hexdigest()


def verify_session_context(
    *,
    encoded_context: str | None,
    signature: str | None,
    secret: str,
) -> TrustedSessionContext:
    if not encoded_context or not signature:
        raise InternalAuthError("signed session context is required")
    expected = sign_session_context(encoded_context, secret=secret)
    if not hmac.compare_digest(signature, expected):
        raise InternalAuthError("invalid session context signature")
    try:
        decoded = _base64url_decode(encoded_context).decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise InternalAuthError("invalid session context encoding") from exc
    context = TrustedSessionContext.model_validate_json(decoded)
    if context.expires_at <= datetime.now(UTC):
        raise InternalAuthError("signed session context has expired")
    return context


def _base64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def trusted_context_payload(context: TrustedSessionContext) -> dict[str, Any]:
    return context.model_dump(mode="json")

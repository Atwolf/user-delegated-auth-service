from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

AccessTokenType: TypeAlias = Literal["urn:ietf:params:oauth:token-type:access_token"]
ACCESS_TOKEN_TYPE: AccessTokenType = "urn:ietf:params:oauth:token-type:access_token"


def _normalize_scopes(value: object, *, allow_empty: bool) -> tuple[str, ...]:
    if isinstance(value, str):
        raise ValueError("scopes must be a sequence of strings, not a string")

    if not isinstance(value, Iterable):
        raise ValueError("scopes must be a sequence of strings")

    normalized: list[str] = []
    seen: set[str] = set()

    for raw_scope in cast(Iterable[object], value):
        if not isinstance(raw_scope, str):
            raise ValueError("each scope must be a string")

        scope = raw_scope.strip()
        if not scope:
            raise ValueError("scopes must not contain blank values")

        if scope not in seen:
            seen.add(scope)
            normalized.append(scope)

    if not normalized and not allow_empty:
        raise ValueError("at least one scope is required")

    return tuple(normalized)


class TokenExchangeRequest(BaseModel):
    """Validated OBO token exchange request sent to the token broker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_token: str = Field(min_length=1, repr=False)
    requested_scopes: tuple[str, ...] = Field(min_length=1)
    subject_token_type: AccessTokenType = ACCESS_TOKEN_TYPE
    audience: str | None = Field(default=None, min_length=1)
    actor: str | None = Field(default=None, min_length=1)

    @field_validator("requested_scopes", mode="before")
    @classmethod
    def _validate_requested_scopes(cls, value: object) -> tuple[str, ...]:
        return _normalize_scopes(value, allow_empty=False)


class TokenExchangeResponse(BaseModel):
    """Raw access-token response returned by the token broker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    access_token: str = Field(min_length=1, repr=False)
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int | None = Field(default=None, ge=1)
    scopes: tuple[str, ...] = Field(default_factory=tuple)
    issued_token_type: AccessTokenType = ACCESS_TOKEN_TYPE

    @field_validator("scopes", mode="before")
    @classmethod
    def _validate_scopes(cls, value: object) -> tuple[str, ...]:
        return _normalize_scopes(value, allow_empty=True)


class WorkflowTokenExchangeRequest(BaseModel):
    """Workflow-scoped OBO token request used by the supervisor."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    workflow_id: str = Field(..., min_length=1)
    approval_id: str = Field(..., min_length=1)
    plan_hash: str = Field(..., min_length=1)

    tenant_id: str | None = None
    auth_context_ref: str = Field(..., min_length=1)

    requested_scopes: list[str] = Field(default_factory=list)
    requested_audience: str | None = None
    ttl_seconds: int | None = Field(default=None, gt=0)

    @field_validator("requested_scopes")
    @classmethod
    def _normalize_requested_scopes(cls, value: list[str]) -> list[str]:
        return sorted(_normalize_scopes(value, allow_empty=True))


class WorkflowTokenExchangeResponse(BaseModel):
    """Raw access token response returned to workflow callers."""

    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(..., min_length=1, repr=False)
    expires_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    scopes: list[str] = Field(default_factory=list)
    audience: str | None = None

    @field_validator("scopes")
    @classmethod
    def _normalize_scopes(cls, value: list[str]) -> list[str]:
        return sorted(_normalize_scopes(value, allow_empty=True))


class Auth0OnBehalfOfConfig(BaseModel):
    """Auth0 user-delegated OBO token exchange configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: str = Field(..., min_length=1)
    token_endpoint: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: SecretStr = Field(..., min_length=1, repr=False)
    audience: str = Field(..., min_length=1)

    @field_validator("domain")
    @classmethod
    def _normalize_domain(cls, value: str) -> str:
        domain = value.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
        if not domain:
            raise ValueError("domain must not be blank")
        return domain

    @field_validator("token_endpoint")
    @classmethod
    def _validate_endpoint(cls, value: str) -> str:
        endpoint = value.strip()
        if not endpoint.startswith(("https://", "http://")):
            raise ValueError("endpoint must be an HTTP(S) URL")
        return endpoint


class Auth0ClientCredentialsConfig(BaseModel):
    """Validated Auth0 Client Credentials configuration for sample app identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: str = Field(..., min_length=1)
    token_endpoint: str = Field(..., min_length=1)
    jwks_endpoint: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: SecretStr = Field(..., min_length=1, repr=False)
    scopes: tuple[str, ...] = Field(default_factory=tuple)
    audience: str | None = Field(default=None, min_length=1)

    @field_validator("domain")
    @classmethod
    def _normalize_domain(cls, value: str) -> str:
        domain = value.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
        if not domain:
            raise ValueError("domain must not be blank")
        return domain

    @field_validator("token_endpoint", "jwks_endpoint")
    @classmethod
    def _validate_endpoint(cls, value: str) -> str:
        endpoint = value.strip()
        if not endpoint.startswith(("https://", "http://")):
            raise ValueError("endpoint must be an HTTP(S) URL")
        return endpoint

    @field_validator("scopes", mode="before")
    @classmethod
    def _validate_scopes(cls, value: object) -> tuple[str, ...]:
        return _normalize_scopes(value, allow_empty=True)


class Auth0ClientCredentialsTokenResponse(BaseModel):
    """Auth0 Client Credentials token response returned to trusted callers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    access_token: str = Field(..., min_length=1, repr=False)
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int | None = Field(default=None, ge=1)
    scopes: tuple[str, ...] = Field(default_factory=tuple)
    audience: str | None = Field(default=None, min_length=1)
    token_ref: str = Field(..., min_length=1)

    @classmethod
    def from_access_token(
        cls,
        *,
        access_token: str,
        token_type: str,
        expires_in: int | None,
        scopes: Iterable[str],
        audience: str | None,
    ) -> Auth0ClientCredentialsTokenResponse:
        if token_type.lower() != "bearer":
            raise ValueError("token_type must be Bearer")

        digest = sha256(access_token.encode("utf-8")).hexdigest()[:16]
        return cls(
            access_token=access_token,
            expires_in=expires_in,
            scopes=tuple(scopes),
            audience=audience,
            token_ref=f"auth0:{digest}",
        )

    @field_validator("scopes", mode="before")
    @classmethod
    def _validate_scopes(cls, value: object) -> tuple[str, ...]:
        return _normalize_scopes(value, allow_empty=True)

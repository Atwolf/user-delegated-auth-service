from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserPersona(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(..., min_length=1)
    headline: str = Field(..., min_length=1)
    greeting: str = Field(..., min_length=1)
    traits: list[str] = Field(default_factory=list[str])


class Auth0UserSessionMetadataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    token_ref: str = Field(..., min_length=1)
    token_scopes: list[str] = Field(default_factory=list[str])
    tenant_id: str | None = Field(default=None, min_length=1)
    audience: str | None = None
    user_email: str | None = Field(default=None, min_length=1)
    user_name: str | None = Field(default=None, min_length=1)

    @field_validator("token_scopes")
    @classmethod
    def _normalize_token_scopes(cls, value: list[str]) -> list[str]:
        return sorted({scope.strip() for scope in value if scope.strip()})


class Auth0UserSessionMetadataResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str = ""
    audience: str | None = None
    token_ref: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    user_email: str | None = None
    allowed_tools: list[str] = Field(default_factory=list[str])
    persona: UserPersona

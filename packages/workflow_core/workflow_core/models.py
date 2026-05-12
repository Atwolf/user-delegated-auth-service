from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

STRICT_MODEL_CONFIG = ConfigDict(extra="forbid", strict=True)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _dedupe_sorted(values: list[str]) -> list[str]:
    _require_non_empty_strings(values)
    return sorted(set(values))


def _require_non_empty_strings(values: list[str]) -> None:
    if any(value == "" for value in values):
        raise ValueError("values must be non-empty strings")


class ToolProposal(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    agent_name: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)
    reason: str | None = None

    @field_validator("arguments")
    @classmethod
    def _validate_argument_names(
        cls,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        _require_non_empty_strings(list(arguments))
        return arguments


class ToolIntent(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    agent_name: str = Field(..., min_length=1)
    mcp_server: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)
    reason: str | None = None
    metadata_ref: str = Field(..., min_length=1)

    @field_validator("arguments")
    @classmethod
    def _validate_argument_names(
        cls,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        _require_non_empty_strings(list(arguments))
        return arguments


class ScopeRequirement(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    scope_template: str = Field(..., min_length=1)
    scope_args: list[str] = Field(default_factory=list)
    op: str = Field(..., min_length=1)
    hitl_description: str = Field(..., min_length=1)

    @field_validator("scope_args")
    @classmethod
    def _validate_scope_args(cls, scope_args: list[str]) -> list[str]:
        _require_non_empty_strings(scope_args)
        return scope_args


class AuthorizationBundle(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    workflow_id: str = Field(..., min_length=1)
    scopes: list[str] = Field(default_factory=list)
    proposals: list[ToolProposal] = Field(default_factory=list[ToolProposal])

    @field_validator("scopes")
    @classmethod
    def _normalize_scopes(cls, scopes: list[str]) -> list[str]:
        return _dedupe_sorted(scopes)


class WorkflowStep(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    step_id: str = Field(..., min_length=1)
    target_agent: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    input_model_type: str = Field(..., min_length=1)
    input_payload_json: str = Field(..., min_length=2)

    required_scopes: list[str] = Field(default_factory=list)
    downstream_audience: str | None = None
    operation_type: Literal["READ", "WRITE", "ADMIN"] = "READ"
    blast_radius: Literal["none", "low", "medium", "high"] = "low"
    hitl_description: str = "Review workflow step before execution"
    mutates_external_state: bool = False

    @field_validator("required_scopes")
    @classmethod
    def _normalize_required_scopes(cls, scopes: list[str]) -> list[str]:
        return _dedupe_sorted(scopes)


class WorkflowPolicyDecision(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    requires_hitl: bool
    blast_radius: Literal["none", "low", "medium", "high"]
    human_description: str = Field(..., min_length=1)
    required_scopes: list[str] = Field(default_factory=list)
    denied_reason: str | None = None

    @field_validator("required_scopes")
    @classmethod
    def _normalize_required_scopes(cls, scopes: list[str]) -> list[str]:
        return _dedupe_sorted(scopes)


class ExecutionGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(..., min_length=1)
    approval_id: str = Field(..., min_length=1)
    plan_hash: str = Field(..., min_length=1)
    step_id: str = Field(..., min_length=1)
    primitive: Literal["DISCOVERY", "READ", "EXECUTE", "MUTATION"]
    method: Literal["GET", "POST"]
    target_mcp: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)
    required_scopes: list[str] = Field(default_factory=list)
    audience: str | None = Field(default=None, min_length=1)
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    tenant_id: str | None = Field(default=None, min_length=1)
    approved_by_user_id: str = Field(..., min_length=1)
    expires_at: datetime | None = None
    correlation_id: str = Field(..., min_length=1)

    @field_validator("arguments")
    @classmethod
    def _validate_argument_names(
        cls,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        _require_non_empty_strings(list(arguments))
        return arguments

    @field_validator("primitive", "method", mode="before")
    @classmethod
    def _normalize_uppercase(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("required_scopes")
    @classmethod
    def _normalize_required_scopes(cls, scopes: list[str]) -> list[str]:
        return _dedupe_sorted(scopes)


class EgressRequest(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    primitive: Literal["DISCOVERY", "READ", "EXECUTE", "MUTATION"]
    method: Literal["GET", "POST"]
    target_mcp: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)
    workflow_id: str = Field(..., min_length=1)
    approval_id: str | None = Field(default=None, min_length=1)
    obo_token_ref: str | None = Field(default=None, min_length=1)
    execution_grant: ExecutionGrant | None = None
    execution_grant_signature: str | None = Field(default=None, min_length=1)
    token_scopes: list[str] = Field(default_factory=list)
    token_audience: str | None = Field(default=None, min_length=1)

    @field_validator("arguments")
    @classmethod
    def _validate_argument_names(
        cls,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        _require_non_empty_strings(list(arguments))
        return arguments

    @field_validator("primitive", "method", mode="before")
    @classmethod
    def _normalize_uppercase(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("token_scopes")
    @classmethod
    def _normalize_token_scopes(cls, scopes: list[str]) -> list[str]:
        return _dedupe_sorted(scopes)


class WorkflowPlan(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    workflow_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    tenant_id: str | None = None

    created_at: datetime = Field(default_factory=_utc_now)
    steps: list[WorkflowStep]


class ApprovedWorkflow(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    workflow_id: str = Field(..., min_length=1)
    approval_id: str = Field(..., min_length=1)
    plan_hash: str = Field(..., min_length=1)

    approved_at: datetime = Field(default_factory=_utc_now)
    approved_by_user_id: str = Field(..., min_length=1)

    approved_scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None

    @field_validator("approved_scopes")
    @classmethod
    def _normalize_approved_scopes(cls, scopes: list[str]) -> list[str]:
        return _dedupe_sorted(scopes)


class WorkflowStatus(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    status: Literal[
        "created",
        "planned",
        "awaiting_approval",
        "approved",
        "executing",
        "completed",
        "failed",
        "cancelled",
    ] = "created"

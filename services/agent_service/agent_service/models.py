from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from workflow_core import ApprovedWorkflow, ToolIntent, WorkflowPlan, WorkflowPolicyDecision

STRICT_MODEL_CONFIG = ConfigDict(extra="forbid", strict=True)


def utc_now() -> datetime:
    return datetime.now(UTC)


def empty_messages() -> list[dict[str, Any]]:
    return []


class AgentDescriptor(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)


class AgentListResponse(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    agents: list[AgentDescriptor]


class PlanWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    query: str = Field(..., min_length=1, validation_alias=AliasChoices("query", "question"))
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    thread_id: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("thread_id", "threadId"),
    )
    auth_context_ref: str | None = Field(default=None, min_length=1)
    token_ref: str | None = Field(default=None, min_length=1)
    token_scopes: list[str] = Field(default_factory=list)
    allowed_tools: list[str] | None = None
    tenant_id: str | None = Field(default=None, min_length=1)
    messages: list[dict[str, Any]] = Field(default_factory=empty_messages)
    state: dict[str, Any] = Field(default_factory=dict)

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


class RunAgentRequest(PlanWorkflowRequest):
    run_id: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("run_id", "runId"),
    )


class SanitizedWorkflowContext(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    query: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    tenant_id: str | None = Field(default=None, min_length=1)
    token_ref: str | None = Field(default=None, min_length=1)
    token_scopes: list[str] = Field(default_factory=list)
    allowed_tools: list[str] | None = None

    @classmethod
    def from_request(cls, request: PlanWorkflowRequest) -> SanitizedWorkflowContext:
        return cls(
            query=request.query,
            user_id=request.user_id,
            session_id=request.session_id,
            tenant_id=request.tenant_id,
            token_ref=request.token_ref,
            token_scopes=request.token_scopes,
            allowed_tools=request.allowed_tools,
        )

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


class SessionRecord(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    token_ref: str | None = None
    auth_context_ref: str | None = Field(default=None, repr=False)
    token_scopes: list[str] = Field(default_factory=list)
    allowed_tools: list[str] | None = None
    tenant_id: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class TokenRegistryRecord(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    tenant_id: str | None = None
    token_ref: str = Field(..., min_length=1)
    auth_context_ref: str = Field(..., min_length=1, repr=False)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowRecord(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    workflow_id: str = Field(..., min_length=1)
    thread_id: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("thread_id", "threadId"),
    )
    session_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    tenant_id: str | None = Field(default=None, min_length=1)
    status: Literal[
        "awaiting_approval",
        "ready",
        "approved",
        "executing",
        "completed",
        "failed",
        "cancelled",
    ] = "awaiting_approval"
    proposal: WorkflowPlan
    plan_hash: str = Field(..., min_length=1)
    tool_intents: list[ToolIntent] = Field(default_factory=list[ToolIntent])
    policy: WorkflowPolicyDecision
    token_ref: str | None = Field(default=None, min_length=1)
    approved_workflow: ApprovedWorkflow | None = None
    egress_results: list[dict[str, object]] = Field(default_factory=list[dict[str, object]])
    created_at: datetime = Field(default_factory=utc_now)


class PlanWorkflowResponse(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    workflow: WorkflowRecord


class WorkflowApprovalRequest(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    approved: bool
    user_id: str | None = Field(default=None, min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    tenant_id: str | None = Field(default=None, min_length=1)
    approved_by_user_id: str | None = Field(default=None, min_length=1)
    plan_hash: str = Field(..., min_length=1)


class WorkflowApprovalResponse(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    workflow: WorkflowRecord
    token_exchange: dict[str, object] = Field(default_factory=dict[str, object])


class TokenContextRegistrationRequest(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    user_id: str | None = Field(default=None, min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    tenant_id: str | None = Field(default=None, min_length=1)
    token_ref: str = Field(..., min_length=1)
    auth_context_ref: str = Field(..., min_length=1)
    token_scopes: list[str] = Field(default_factory=list)
    allowed_tools: list[str] | None = None

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


class ThreadCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    thread_id: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("thread_id", "threadId"),
    )
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    tenant_id: str | None = Field(default=None, min_length=1)
    token_ref: str | None = Field(default=None, min_length=1)
    auth_context_ref: str | None = Field(default=None, min_length=1)
    token_scopes: list[str] = Field(default_factory=list)
    allowed_tools: list[str] | None = None
    title: str | None = Field(default=None, min_length=1)
    messages: list[dict[str, Any]] = Field(default_factory=empty_messages)
    state: dict[str, Any] = Field(default_factory=dict)

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


class ThreadRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    thread_id: str = Field(..., min_length=1, serialization_alias="threadId")
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    tenant_id: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=empty_messages)
    state: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None
    token_ref: str | None = Field(default=None, min_length=1)
    active_workflow_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ThreadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    thread: ThreadRecord

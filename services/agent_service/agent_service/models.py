from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from workflow_core import ApprovedWorkflow, ToolIntent, WorkflowPlan, WorkflowPolicyDecision

STRICT_MODEL_CONFIG = ConfigDict(extra="forbid", strict=True)


def utc_now() -> datetime:
    return datetime.now(UTC)


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
    auth_context_ref: str | None = Field(default=None, min_length=1)
    token_ref: str | None = Field(default=None, min_length=1)
    token_scopes: list[str] = Field(default_factory=list)
    allowed_tools: list[str] | None = None
    tenant_id: str | None = Field(default=None, min_length=1)

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


class WorkflowRecord(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    workflow_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
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
    auth_context_ref: str | None = Field(default=None, min_length=1, exclude=True, repr=False)
    approved_workflow: ApprovedWorkflow | None = None
    egress_results: list[dict[str, object]] = Field(default_factory=list[dict[str, object]])
    created_at: datetime = Field(default_factory=utc_now)


class PlanWorkflowResponse(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    workflow: WorkflowRecord


class WorkflowApprovalRequest(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    approved: bool
    approved_by_user_id: str = Field(..., min_length=1)
    plan_hash: str = Field(..., min_length=1)


class WorkflowApprovalResponse(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    workflow: WorkflowRecord
    token_exchange: dict[str, object] = Field(default_factory=dict[str, object])

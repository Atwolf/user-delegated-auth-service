from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from workflow_core.models import (
    ApprovedWorkflow,
    AuthorizationBundle,
    WorkflowPlan,
    WorkflowStatus,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


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


class WorkflowPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1)
    user_id: str = Field(default="sample-user", min_length=1)
    session_id: str = Field(default="sample-session", min_length=1)
    tenant_id: str | None = Field(default=None, min_length=1)
    auth_context_ref: str | None = Field(default=None, min_length=1)
    token_ref: str | None = Field(default=None, min_length=1)
    token_scopes: list[str] = Field(default_factory=list)
    allowed_tools: list[str] | None = None

    @field_validator("token_scopes")
    @classmethod
    def _normalize_token_scopes(cls, value: list[str]) -> list[str]:
        return sorted({scope.strip() for scope in value if scope.strip()})

    @field_validator("allowed_tools")
    @classmethod
    def _normalize_allowed_tools(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return sorted({tool.strip() for tool in value if tool.strip()})


class WorkflowApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    approved_by_user_id: str = Field(default="sample-user", min_length=1)
    plan_hash: str = Field(..., min_length=1)
    token_ref: str | None = Field(default=None, min_length=1)


class WorkflowTimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    step_id: str | None = None
    attributes: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class WorkflowStepExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(..., min_length=1)
    target_agent: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    status: Literal["completed", "failed"] = "completed"
    output: dict[str, object] = Field(default_factory=dict)


class WorkflowRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(..., min_length=1)
    status: WorkflowStatus
    plan: WorkflowPlan
    plan_hash: str = Field(..., min_length=1)
    authorization: AuthorizationBundle
    approved_workflow: ApprovedWorkflow | None = None
    events: list[WorkflowTimelineEvent] = Field(default_factory=list[WorkflowTimelineEvent])
    step_results: list[WorkflowStepExecutionResult] = Field(
        default_factory=list[WorkflowStepExecutionResult]
    )
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

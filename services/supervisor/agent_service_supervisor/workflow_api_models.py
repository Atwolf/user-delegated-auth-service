from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from workflow_core.models import (
    ApprovedWorkflow,
    AuthorizationBundle,
    WorkflowPlan,
    WorkflowStatus,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Auth0ClientCredentialsTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str = Field(..., min_length=1)
    token_endpoint: str = Field(..., min_length=1)
    jwks_endpoint: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: SecretStr | None = Field(default=None, repr=False)
    scope: str = ""
    audience: str | None = Field(default=None, min_length=1)
    user_id: str = Field(default="sample-user", min_length=1)
    session_id: str = Field(default="sample-session", min_length=1)

    @field_validator("scope")
    @classmethod
    def _normalize_scope(cls, value: str) -> str:
        return " ".join(part for part in value.split(" ") if part)


class Auth0ClientCredentialsTokenResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(..., min_length=1, repr=False)
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int | None = Field(default=None, ge=1)
    scope: str = ""
    audience: str | None = None
    token_ref: str = Field(..., min_length=1)


class WorkflowPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1)
    user_id: str = Field(default="sample-user", min_length=1)
    session_id: str = Field(default="sample-session", min_length=1)
    tenant_id: str | None = Field(default=None, min_length=1)
    auth_context_ref: str | None = Field(default=None, min_length=1)
    token_ref: str | None = Field(default=None, min_length=1)


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

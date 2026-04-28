from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

STRICT_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    strict=True,
    validate_assignment=True,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class WorkflowStep(BaseModel):
    """Lightweight workflow step snapshot stored with session state."""

    model_config = STRICT_MODEL_CONFIG

    step_id: str = Field(..., min_length=1)
    target_agent: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    input_model_type: str = Field(..., min_length=1)
    input_payload_json: str = Field(..., min_length=2)

    required_scopes: list[str] = Field(default_factory=list)
    downstream_audience: str | None = None
    mutates_external_state: bool = False


class WorkflowPlan(BaseModel):
    """Workflow plan snapshot stored as a Pydantic JSON blob.

    The workflow-core package owns canonical workflow behavior. This local model
    keeps Redis persistence usable without importing sibling worktree packages.
    """

    model_config = STRICT_MODEL_CONFIG

    workflow_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    tenant_id: str | None = None

    created_at: datetime = Field(default_factory=utc_now)
    steps: list[WorkflowStep]


class ApprovedWorkflow(BaseModel):
    """Approved workflow snapshot stored with workflow state."""

    model_config = STRICT_MODEL_CONFIG

    workflow_id: str = Field(..., min_length=1)
    approval_id: str = Field(..., min_length=1)
    plan_hash: str = Field(..., min_length=1)

    approved_at: datetime = Field(default_factory=utc_now)
    approved_by_user_id: str = Field(..., min_length=1)

    approved_scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


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


class SessionState(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    tenant_id: str | None = None
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)

    auth_context_ref: str = Field(..., min_length=1)
    active_workflow_id: str | None = None

    version: int = Field(default=0, ge=0)
    values: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowState(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    tenant_id: str | None = None
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    workflow_id: str = Field(..., min_length=1)

    plan: WorkflowPlan | None = None
    approved_workflow: ApprovedWorkflow | None = None
    status: WorkflowStatus

    version: int = Field(default=0, ge=0)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

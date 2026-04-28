from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from workflow_core import ApprovedWorkflow, WorkflowPlan, WorkflowStatus, WorkflowStep

__all__ = [
    "ApprovedWorkflow",
    "SessionState",
    "WorkflowPlan",
    "WorkflowState",
    "WorkflowStatus",
    "WorkflowStep",
]

STRICT_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    strict=True,
    validate_assignment=True,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


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

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator

OtelScalar: TypeAlias = str | bool | int | float
OtelAttributeValue: TypeAlias = OtelScalar | list[OtelScalar]


class WorkflowEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)

    tenant_id: str | None = None
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    workflow_id: str | None = None
    step_id: str | None = None

    agent_name: str | None = None
    agentic_span_id: str = Field(..., min_length=1)
    parent_agentic_span_id: str | None = None
    trace_id: str | None = None

    plan_hash: str | None = None
    approval_id: str | None = None
    idempotency_key: str | None = None

    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class WorkflowOtelEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    attributes: dict[str, OtelAttributeValue] = Field(default_factory=dict)

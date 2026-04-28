from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

PayloadT = TypeVar("PayloadT", bound=BaseModel)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017


class StrictA2APayload(BaseModel):
    """Base class for action-specific A2A payload contracts."""

    model_config = ConfigDict(extra="forbid", strict=True)


class A2AEnvelope(BaseModel, Generic[PayloadT]):
    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)

    from_agent: str = Field(..., min_length=1)
    to_agent: str = Field(..., min_length=1)

    tenant_id: str | None = None
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    workflow_id: str | None = None

    agentic_span_id: str = Field(..., min_length=1)
    parent_agentic_span_id: str | None = None
    trace_id: str | None = None

    plan_hash: str | None = None
    approval_id: str | None = None
    step_id: str | None = None

    auth_context_ref: str = Field(..., min_length=1)
    obo_token_ref: str | None = None

    created_at: datetime = Field(default_factory=_utc_now)
    payload: PayloadT

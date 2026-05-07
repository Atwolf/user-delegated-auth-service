from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AgentInvocationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str | None = None
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    workflow_id: str | None = None

    agentic_span_id: str = Field(..., min_length=1)
    parent_agentic_span_id: str | None = None
    trace_id: str | None = None

    calling_agent: str = Field(..., min_length=1)
    target_agent: str = Field(..., min_length=1)

    plan_hash: str | None = None
    approval_id: str | None = None
    step_id: str | None = None

    auth_context_ref: str = Field(..., min_length=1)
    obo_token_ref: str | None = None

    idempotency_key: str = Field(..., min_length=1)

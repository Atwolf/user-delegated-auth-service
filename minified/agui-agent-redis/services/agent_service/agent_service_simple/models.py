from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AgUiMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    role: str | None = None
    content: str | list[dict[str, Any]] | None = None


class UserContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., min_length=1)
    token_ref: str = Field(..., min_length=1)
    auth_scheme: str = "bearer"


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    thread_id: str = Field(..., validation_alias=AliasChoices("threadId", "thread_id"))
    run_id: str = Field(..., validation_alias=AliasChoices("runId", "run_id"))
    parent_run_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("parentRunId", "parent_run_id"),
    )
    session_id: str = Field(..., validation_alias=AliasChoices("sessionId", "session_id"))
    messages: list[AgUiMessage] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    context: list[dict[str, Any]] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    forwarded_props: Any = Field(
        default_factory=dict,
        validation_alias=AliasChoices("forwardedProps", "forwarded_props"),
    )
    user: UserContext


class ThreadCacheEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    thread_id: str
    session_id: str
    agent_session_id: str
    token_ref: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    run_count: int = 0
    updated_at: str = Field(default_factory=utc_now_iso)


class RuntimeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    routed_agent: str
    runtime_mode: str

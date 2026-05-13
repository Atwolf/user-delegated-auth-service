from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class AgUiMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    role: str | None = None
    content: str | list[dict[str, Any]] | None = None


class RunAgentInput(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    thread_id: str = Field(..., validation_alias=AliasChoices("threadId", "thread_id"))
    run_id: str = Field(..., validation_alias=AliasChoices("runId", "run_id"))
    parent_run_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("parentRunId", "parent_run_id"),
    )
    messages: list[AgUiMessage] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    context: list[dict[str, Any]] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    forwarded_props: Any = Field(
        default_factory=dict,
        validation_alias=AliasChoices("forwardedProps", "forwarded_props"),
    )


class UserContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    auth_scheme: str = "bearer"

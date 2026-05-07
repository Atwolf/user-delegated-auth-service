from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class AgUiMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str | None = None
    content: str | list[dict[str, Any]] | None = None


class RunAgentInput(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    thread_id: str = Field(..., validation_alias=AliasChoices("threadId", "thread_id"))
    run_id: str = Field(..., validation_alias=AliasChoices("runId", "run_id"))
    messages: list[AgUiMessage] = Field(default_factory=list[AgUiMessage])
    state: dict[str, Any] = Field(default_factory=dict)


def default_input_schema() -> dict[str, object]:
    return {
        "threadId": "string",
        "runId": "string",
        "messages": "array",
        "state": "object",
    }


class AgentCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str = "ag-ui-gateway"
    protocol: str = "ag-ui"
    endpoints: list[str] = Field(
        default_factory=lambda: ["GET /healthz", "GET /agent/capabilities", "POST /agent"]
    )
    input_schema: dict[str, object] = Field(default_factory=default_input_schema)
    event_types: list[str] = Field(
        default_factory=lambda: [
            "RUN_STARTED",
            "TEXT_MESSAGE_CONTENT",
            "STATE_DELTA",
            "CUSTOM",
            "RUN_FINISHED",
        ]
    )

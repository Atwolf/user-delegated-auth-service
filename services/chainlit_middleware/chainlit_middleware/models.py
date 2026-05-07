from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChainlitMessageEvent(BaseModel):
    thread_id: str = Field(..., min_length=1)
    user_id: str | None = Field(default=None, min_length=1)
    content: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChainlitApprovalEvent(BaseModel):
    workflow_id: str = Field(..., min_length=1)
    plan_hash: str = Field(..., min_length=1)


class CopilotWidgetMetadata(BaseModel):
    name: str
    mount_id: str
    transport: str
    events_endpoint: str


class CopilotConfig(BaseModel):
    ag_ui_gateway_url: str
    widget: CopilotWidgetMetadata


class ChainlitForwardResponse(BaseModel):
    thread_id: str
    forwarded: bool
    ag_ui_status: int | None
    summary: str | None = None
    workflow: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    events: list[dict[str, Any]] = Field(default_factory=lambda: [])

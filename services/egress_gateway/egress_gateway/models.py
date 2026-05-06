from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from workflow_core import EgressRequest as WorkflowEgressRequest


class EgressRequest(WorkflowEgressRequest):
    access_token: str | None = None


class EgressResponse(BaseModel):
    primitive: str
    method: str
    target_mcp: str
    tool_name: str
    arguments: dict[str, Any]
    workflow_id: str
    approval_id: str | None = None
    obo_token_ref: str | None = None
    outbound: dict[str, Any]

from __future__ import annotations

from agent_runtime import create_agent_app
from pydantic import BaseModel, ConfigDict, Field
from workflow_core import ToolProposal


class CapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)


class CapabilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposals: list[ToolProposal] = Field(default_factory=list[ToolProposal])


app = create_agent_app("planner-agent")


@app.post("/capabilities", response_model=CapabilityResponse)
async def capabilities(request: CapabilityRequest) -> CapabilityResponse:
    return CapabilityResponse(
        proposals=[
            ToolProposal(
                agent_name="planner",
                tool_name="propose_workflow_plan",
                arguments={"query": request.query},
                reason="Planner scaffold",
            )
        ]
    )

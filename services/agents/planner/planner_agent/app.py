from __future__ import annotations

from fastapi import FastAPI
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


app = FastAPI(title="planner-agent")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


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

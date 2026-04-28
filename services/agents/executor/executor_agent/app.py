from __future__ import annotations

from agent_runtime import create_agent_app
from pydantic import BaseModel, ConfigDict, Field


class ExecuteStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(..., min_length=1)
    step_id: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)


class ExecuteStepResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(..., min_length=1)
    step_id: str = Field(..., min_length=1)
    status: str = "completed"
    result: dict[str, object] = Field(default_factory=dict)


app = create_agent_app("executor-agent")


@app.post("/execute", response_model=ExecuteStepResponse)
async def execute(request: ExecuteStepRequest) -> ExecuteStepResponse:
    return ExecuteStepResponse(
        workflow_id=request.workflow_id,
        step_id=request.step_id,
        result={"action": request.action, "arguments": request.arguments},
    )

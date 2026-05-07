from __future__ import annotations

from agent_runtime import create_agent_app
from pydantic import BaseModel, ConfigDict, Field


class AuthorizationGateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(..., min_length=1)
    scopes: list[str] = Field(default_factory=list)
    user_id: str = Field(..., min_length=1)


class AuthorizationGateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str = Field(..., min_length=1)
    approved_scopes: list[str] = Field(default_factory=list)


app = create_agent_app("authorizer-agent")


@app.post("/authorize", response_model=AuthorizationGateResponse)
async def authorize(request: AuthorizationGateRequest) -> AuthorizationGateResponse:
    return AuthorizationGateResponse(
        approval_id=f"approval:{request.workflow_id}",
        approved_scopes=sorted(set(request.scopes)),
    )

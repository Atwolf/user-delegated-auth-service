from __future__ import annotations

from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from ag_ui_gateway.client import AgentServiceClient, HttpAgentServiceClient
from ag_ui_gateway.models import AgentCapabilities, RunAgentInput
from ag_ui_gateway.sse import stream_agent_events


def create_app(agent_service: AgentServiceClient | None = None) -> FastAPI:
    app = FastAPI(title="AG-UI Gateway")
    app.state.agent_service = agent_service or HttpAgentServiceClient()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/agent/capabilities", response_model=AgentCapabilities)
    async def capabilities() -> AgentCapabilities:
        return AgentCapabilities()

    @app.post("/agent")
    async def run_agent(payload: RunAgentInput, request: Request) -> StreamingResponse:
        service = cast(AgentServiceClient, request.app.state.agent_service)
        return StreamingResponse(
            stream_agent_events(payload, service),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return app


app = create_app()

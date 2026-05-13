from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from gateway_app.auth import user_context_from_request
from gateway_app.forwarding import forward_agent_run
from gateway_app.schemas import RunAgentInput


def create_app() -> FastAPI:
    app = FastAPI(title="AG-UI Gateway")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/agent/capabilities")
    async def capabilities() -> dict[str, object]:
        return {
            "service": "ag-ui-gateway",
            "protocol": "ag-ui",
            "endpoints": ["GET /healthz", "GET /agent/capabilities", "POST /agent"],
            "event_types": [
                "RUN_STARTED",
                "TEXT_MESSAGE_START",
                "TEXT_MESSAGE_CONTENT",
                "TEXT_MESSAGE_END",
                "STATE_DELTA",
                "RUN_FINISHED",
                "RUN_ERROR",
            ],
        }

    @app.post("/agent")
    async def run_agent(payload: RunAgentInput, request: Request) -> StreamingResponse:
        user_context = user_context_from_request(request)
        return StreamingResponse(
            forward_agent_run(payload, user_context),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()

from __future__ import annotations

import os
from typing import cast

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from session_state import (
    SESSION_CONTEXT_HEADER,
    SESSION_CONTEXT_SIGNATURE_HEADER,
    InternalAuthError,
    TrustedSessionContext,
    verify_session_context,
)

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
        context = _trusted_context_from_request(request)
        return StreamingResponse(
            stream_agent_events(payload, service, context),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return app


app = create_app()


def _trusted_context_from_request(request: Request) -> TrustedSessionContext:
    try:
        return verify_session_context(
            encoded_context=request.headers.get(SESSION_CONTEXT_HEADER),
            signature=request.headers.get(SESSION_CONTEXT_SIGNATURE_HEADER),
            secret=_internal_auth_secret(),
        )
    except InternalAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


def _internal_auth_secret() -> str:
    return os.getenv("INTERNAL_SERVICE_AUTH_SECRET") or ""

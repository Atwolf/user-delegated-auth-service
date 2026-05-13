from __future__ import annotations

from collections.abc import AsyncIterator

from ag_ui.core import EventType, RunAgentInput, RunErrorEvent
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from adk_agent_service.auth import user_context_from_request
from adk_agent_service.contracts import AgentRunRequest
from adk_agent_service.request_normalization import agent_run_request_from_agui
from adk_agent_service.runtime.adk_runner import stream_adk_events
from adk_agent_service.runtime.agent import AGENT_NAME
from adk_agent_service.stores.factory import build_thread_metadata_store
from adk_agent_service.stores.thread_metadata import ThreadMetadataStore


def create_app(metadata_store: ThreadMetadataStore | None = None) -> FastAPI:
    app = FastAPI(title="AG-UI ADK Agent Service")
    app.state.metadata_store = metadata_store or build_thread_metadata_store()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/agent/capabilities")
    async def capabilities() -> dict[str, object]:
        return {
            "service": "adk-agent-service",
            "protocol": "ag-ui",
            "agent": {
                "name": AGENT_NAME,
                "description": "Streams AG-UI events from the Google ADK runtime.",
            },
            "endpoints": ["GET /healthz", "GET /agent/capabilities", "POST /agent"],
            "event_types": [
                "RUN_STARTED",
                "TEXT_MESSAGE_START",
                "TEXT_MESSAGE_CONTENT",
                "TEXT_MESSAGE_END",
                "STATE_DELTA",
                "STATE_SNAPSHOT",
                "RUN_FINISHED",
                "RUN_ERROR",
            ],
        }

    @app.post("/agent")
    async def run_agent(input_data: RunAgentInput, request: Request) -> StreamingResponse:
        user_context = user_context_from_request(request)
        payload = agent_run_request_from_agui(input_data, user_context)
        metadata_store = request.app.state.metadata_store
        encoder = EventEncoder(accept=request.headers.get("accept", ""))
        return StreamingResponse(
            run_stream(payload, metadata_store, encoder),
            media_type=encoder.get_content_type(),
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()


async def run_stream(
    payload: AgentRunRequest,
    metadata_store: ThreadMetadataStore,
    encoder: EventEncoder,
) -> AsyncIterator[str]:
    try:
        _, metadata = await metadata_store.upsert_from_run(payload)
        async for event in stream_adk_events(payload, metadata):
            yield encoder.encode(event)
    except Exception as exc:
        yield encoder.encode(
            RunErrorEvent(
                type=EventType.RUN_ERROR,
                message=safe_error(exc),
                code="AGENT_SERVICE_ERROR",
            )
        )


def safe_error(exc: Exception) -> str:
    return (str(exc) or exc.__class__.__name__).replace("\n", " ")[:240]

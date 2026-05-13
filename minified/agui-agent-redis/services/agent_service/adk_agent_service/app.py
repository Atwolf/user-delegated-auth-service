from __future__ import annotations

from collections.abc import AsyncIterator

from ag_ui.core import EventType, RunErrorEvent
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from adk_agent_service.contracts import AgentRunRequest
from adk_agent_service.runtime.adk_runner import stream_adk_events
from adk_agent_service.runtime.agent import AGENT_NAME
from adk_agent_service.stores.redis_thread_metadata import build_thread_metadata_store
from adk_agent_service.stores.thread_metadata import ThreadMetadataStore


def create_app(metadata_store: ThreadMetadataStore | None = None) -> FastAPI:
    app = FastAPI(title="ADK Agent Service")
    app.state.metadata_store = metadata_store or build_thread_metadata_store()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/agents")
    async def agents() -> dict[str, object]:
        return {
            "agents": [
                {
                    "name": AGENT_NAME,
                    "description": "Streams AG-UI events from the Google ADK runtime.",
                },
            ]
        }

    @app.post("/runs/stream")
    async def run_agent(payload: AgentRunRequest, request: Request) -> StreamingResponse:
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

from __future__ import annotations

from collections.abc import AsyncIterator

from ag_ui.core import EventType, RunErrorEvent
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from agent_service_simple.adk_runtime import PersistentAdkRuntime
from agent_service_simple.cache import RedisThreadCache, build_thread_cache
from agent_service_simple.models import AgentRunRequest


def create_app(
    cache: RedisThreadCache | None = None,
    runtime: PersistentAdkRuntime | None = None,
) -> FastAPI:
    app = FastAPI(title="Minified Agent Service")
    app.state.cache = cache or build_thread_cache()
    app.state.runtime = runtime or PersistentAdkRuntime()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/agents")
    async def agents() -> dict[str, object]:
        return {
            "agents": [
                {
                    "name": "coordinator_dispatcher",
                    "description": "Routes each AG-UI run to a stateful specialist process.",
                },
                {
                    "name": "support_agent",
                    "description": "Handles explanatory and troubleshooting requests.",
                },
                {
                    "name": "operations_agent",
                    "description": "Handles runtime, cache, and service-boundary requests.",
                },
            ]
        }

    @app.post("/runs/stream")
    async def run_agent(payload: AgentRunRequest, request: Request) -> StreamingResponse:
        cache_store = request.app.state.cache
        runtime_engine = request.app.state.runtime
        encoder = EventEncoder(accept=request.headers.get("accept", ""))
        return StreamingResponse(
            _run_stream(payload, cache_store, runtime_engine, encoder),
            media_type=encoder.get_content_type(),
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()


async def _run_stream(
    payload: AgentRunRequest,
    cache: RedisThreadCache,
    runtime: PersistentAdkRuntime,
    encoder: EventEncoder,
) -> AsyncIterator[str]:
    try:
        cache_key, cache_entry = await cache.upsert_from_run(payload)
        async for event in runtime.stream_events(payload, cache_key, cache_entry):
            yield encoder.encode(event)
    except Exception as exc:
        yield encoder.encode(
            RunErrorEvent(
                type=EventType.RUN_ERROR,
                message=_safe_error(exc),
                code="AGENT_SERVICE_ERROR",
            )
        )


def _safe_error(exc: Exception) -> str:
    return (str(exc) or exc.__class__.__name__).replace("\n", " ")[:240]

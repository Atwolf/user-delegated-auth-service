from __future__ import annotations

from typing import cast

from fastapi import FastAPI, Request

from observability_sidecar.models import (
    AgenticTraceIngest,
    LogIngest,
    SidecarStats,
    TelemetrySnapshot,
)
from observability_sidecar.store import InMemoryTelemetryStore


def create_app(store: InMemoryTelemetryStore | None = None) -> FastAPI:
    telemetry_store = store or InMemoryTelemetryStore()
    app = FastAPI(title="Observability Sidecar")
    app.state.telemetry_store = telemetry_store

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/traces", response_model=AgenticTraceIngest)
    async def ingest_trace(payload: AgenticTraceIngest, request: Request) -> AgenticTraceIngest:
        store = cast(InMemoryTelemetryStore, request.app.state.telemetry_store)
        return await store.append_trace(payload)

    @app.post("/v1/logs", response_model=LogIngest)
    async def ingest_log(payload: LogIngest, request: Request) -> LogIngest:
        store = cast(InMemoryTelemetryStore, request.app.state.telemetry_store)
        return await store.append_log(payload)

    @app.get("/v1/stats", response_model=SidecarStats)
    async def stats(request: Request) -> SidecarStats:
        store = cast(InMemoryTelemetryStore, request.app.state.telemetry_store)
        return await store.stats()

    @app.get("/v1/telemetry", response_model=TelemetrySnapshot)
    async def telemetry(request: Request) -> TelemetrySnapshot:
        store = cast(InMemoryTelemetryStore, request.app.state.telemetry_store)
        return TelemetrySnapshot(
            traces=await store.traces(),
            logs=await store.logs(),
            stats=await store.stats(),
        )

    @app.get("/v1/monitor/components", response_model=list[str])
    async def components(request: Request) -> list[str]:
        store = cast(InMemoryTelemetryStore, request.app.state.telemetry_store)
        return await store.components()

    @app.get("/v1/monitor/event-types", response_model=list[str])
    async def event_types(request: Request) -> list[str]:
        store = cast(InMemoryTelemetryStore, request.app.state.telemetry_store)
        return await store.event_types()

    return app


app = create_app()

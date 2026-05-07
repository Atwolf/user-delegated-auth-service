from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent_service_supervisor.config import SupervisorSettings
from agent_service_supervisor.discovery_sqlite import SubagentDiscoveryService
from agent_service_supervisor.routes import router
from agent_service_supervisor.workflow_orchestrator import WorkflowOrchestrator


def create_app(settings: SupervisorSettings | None = None) -> FastAPI:
    resolved_settings = settings or SupervisorSettings.from_env()
    discovery = SubagentDiscoveryService(resolved_settings.subagent_db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        await discovery.create_schema()
        app.state.enabled_subagents = await discovery.load_enabled_subagents()
        yield

    app = FastAPI(title="Agent Service Supervisor", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.subagent_discovery = discovery
    app.state.workflow_orchestrator = WorkflowOrchestrator(discovery)
    app.state.workflow_store = {}
    app.include_router(router)
    return app


app = create_app()

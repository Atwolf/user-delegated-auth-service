from __future__ import annotations

from fastapi import FastAPI

from agent_service_supervisor.config import SupervisorSettings
from agent_service_supervisor.routes import router


def create_app(settings: SupervisorSettings | None = None) -> FastAPI:
    app = FastAPI(title="Agent Service Supervisor")
    app.state.settings = settings or SupervisorSettings.from_env()
    app.include_router(router)
    return app


app = create_app()

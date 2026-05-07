from __future__ import annotations

from fastapi import FastAPI


def create_agent_app(title: str) -> FastAPI:
    app = FastAPI(title=title)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app

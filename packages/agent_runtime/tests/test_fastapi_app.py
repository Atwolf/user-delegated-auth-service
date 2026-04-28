from __future__ import annotations

from agent_runtime.fastapi_app import create_agent_app
from fastapi.testclient import TestClient


def test_create_agent_app_registers_healthz() -> None:
    app = create_agent_app("sample-agent")

    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

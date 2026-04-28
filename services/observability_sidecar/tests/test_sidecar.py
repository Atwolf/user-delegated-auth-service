from __future__ import annotations

from fastapi.testclient import TestClient
from observability_sidecar.app import create_app


def test_sidecar_ingests_traces_and_logs_with_redaction() -> None:
    client = TestClient(create_app())

    trace_response = client.post(
        "/v1/traces",
        json={
            "source_component": "supervisor",
            "event": {
                "event_id": "evt-1",
                "event_type": "workflow.planned",
                "user_id": "user-1",
                "session_id": "session-1",
                "agentic_span_id": "span-1",
                "attributes": {"access_token": "secret-token", "appid": "ABCD"},
            },
        },
    )
    assert trace_response.status_code == 200
    assert trace_response.json()["event"]["attributes"]["access_token"] == "[REDACTED]"

    log_response = client.post(
        "/v1/logs",
        json={
            "source_component": "developer-mcp",
            "level": "info",
            "message": "tool called with Bearer abc123",
            "attributes": {"authorization": "Bearer abc123", "appid": "ABCD"},
        },
    )
    assert log_response.status_code == 200
    assert log_response.json()["attributes"]["authorization"] == "[REDACTED]"

    stats = client.get("/v1/stats")
    assert stats.json() == {"trace_count": 1, "log_count": 1}

    components = client.get("/v1/monitor/components")
    assert components.json() == ["developer-mcp", "supervisor"]

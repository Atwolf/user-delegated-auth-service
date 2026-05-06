import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from chainlit_middleware.app import create_app
from chainlit_middleware.config import ChainlitMiddlewareSettings
from fastapi.testclient import TestClient


def test_healthz() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_copilot_config_exposes_gateway_url_and_widget_metadata() -> None:
    client = TestClient(
        create_app(
            ChainlitMiddlewareSettings(
                ag_ui_gateway_url="http://test-gateway.local/agent",
            )
        )
    )

    response = client.get("/copilot/config")

    assert response.status_code == 200
    assert response.json() == {
        "ag_ui_gateway_url": "http://test-gateway.local/agent",
        "widget": {
            "name": "Chainlit Copilot",
            "mount_id": "chainlit-copilot",
            "transport": "ag-ui",
            "events_endpoint": "/chainlit/events/message",
        },
    }


def test_message_event_forwards_chainlit_payload_to_ag_ui_gateway() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = _json_request(request)
        return httpx.Response(
            202,
            text=(
                "event: TEXT_MESSAGE_CONTENT\n"
                'data: {"delta":"Workflow wf-1 is ready with 1 planned step(s)."}\n\n'
                "event: STATE_DELTA\n"
                'data: {"delta":{"workflow":{"workflow_id":"wf-1","status":"ready",'
                '"plan_hash":"sha256:abc","proposal":{"steps":[]},'
                '"policy":{"required_scopes":["read:dns:app.example.com"]}}}}\n\n'
            ),
        )

    client = TestClient(
        create_app(
            ChainlitMiddlewareSettings(
                ag_ui_gateway_url="http://ag-ui.test/agent",
            ),
            http_client_factory=_mock_client_factory(httpx.MockTransport(handler)),
        )
    )

    response = client.post(
        "/chainlit/events/message",
        json={
            "thread_id": "thread-123",
            "user_id": "user-456",
            "content": "Plan my workflow",
            "metadata": {"source": "copilot"},
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "thread_id": "thread-123",
        "forwarded": True,
        "ag_ui_status": 202,
        "summary": "Workflow wf-1 is ready with 1 planned step(s).",
        "workflow": {
            "workflow_id": "wf-1",
            "status": "ready",
            "plan_hash": "sha256:abc",
            "policy": {"required_scopes": ["read:dns:app.example.com"]},
            "proposal": {"steps": []},
            "tool_intents": [],
        },
        "approval": None,
        "events": [
            {
                "event": "TEXT_MESSAGE_CONTENT",
                "data": {"delta": "Workflow wf-1 is ready with 1 planned step(s)."},
            },
            {
                "event": "STATE_DELTA",
                "data": {
                    "delta": {
                        "workflow": {
                            "workflow_id": "wf-1",
                            "status": "ready",
                            "plan_hash": "sha256:abc",
                            "proposal": {"steps": []},
                            "policy": {"required_scopes": ["read:dns:app.example.com"]},
                        }
                    }
                },
            },
        ],
    }
    assert captured["url"] == "http://ag-ui.test/agent"
    assert captured["payload"]["thread_id"] == "thread-123"
    assert captured["payload"]["threadId"] == "thread-123"
    assert captured["payload"]["run_id"]
    assert captured["payload"]["runId"] == captured["payload"]["run_id"]
    assert captured["payload"]["messages"] == [
        {
            "id": captured["payload"]["messages"][0]["id"],
            "role": "user",
            "content": "Plan my workflow",
            "metadata": {
                "source": "copilot",
                "chainlit_user_id": "user-456",
            },
        }
    ]


def test_message_event_reports_gateway_error_status_without_network() -> None:
    client = TestClient(
        create_app(
            ChainlitMiddlewareSettings(
                ag_ui_gateway_url="http://ag-ui.test/agent",
            ),
            http_client_factory=_mock_client_factory(
                httpx.MockTransport(lambda _: httpx.Response(503, json={"error": "busy"}))
            ),
        )
    )

    response = client.post(
        "/chainlit/events/message",
        json={"thread_id": "thread-1", "user_id": "user-1", "content": "hello"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "thread_id": "thread-1",
        "forwarded": False,
        "ag_ui_status": 503,
        "summary": None,
        "workflow": None,
        "approval": None,
        "events": [],
    }


def test_message_event_returns_hitl_approval_metadata_from_ag_ui_sse() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                "event: STATE_DELTA\n"
                'data: {"delta":{"workflow":{"workflow_id":"wf-hitl","status":"awaiting_approval",'
                '"plan_hash":"sha256:hitl","proposal":{"steps":[{"action":"update_firewall_rule"}]},'
                '"policy":{"required_scopes":["write:firewall:fw-sample"]},'
                '"tool_intents":[{"tool_name":"update_firewall_rule"}]}}}\n\n'
                "event: CUSTOM\n"
                'data: {"name":"hitl.approval.requested","value":{"kind":"HITL_APPROVAL",'
                '"workflow_id":"wf-hitl","plan_hash":"sha256:hitl",'
                '"required_scopes":["write:firewall:fw-sample"],'
                '"message":"Update firewall rule for selected rule ID"}}\n\n'
            ),
        )

    client = TestClient(
        create_app(
            ChainlitMiddlewareSettings(ag_ui_gateway_url="http://ag-ui.test/agent"),
            http_client_factory=_mock_client_factory(httpx.MockTransport(handler)),
        )
    )

    response = client.post(
        "/chainlit/events/message",
        json={
            "thread_id": "thread-123",
            "content": "Update firewall rule fw-sample",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow"]["status"] == "awaiting_approval"
    assert payload["workflow"]["workflow_id"] == "wf-hitl"
    assert payload["approval"] == {
        "kind": "HITL_APPROVAL",
        "workflow_id": "wf-hitl",
        "plan_hash": "sha256:hitl",
        "required_scopes": ["write:firewall:fw-sample"],
        "message": "Update firewall rule for selected rule ID",
    }


def test_approval_event_calls_agent_service() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = _json_request(request)
        return httpx.Response(
            200,
            json={
                "workflow": {
                    "workflow_id": "wf-hitl",
                    "status": "completed",
                    "plan_hash": "sha256:hitl",
                    "proposal": {"steps": []},
                    "policy": {"required_scopes": ["write:firewall:fw-sample"]},
                },
                "token_exchange": {
                    "attempted": True,
                    "audience": "https://magnum-opus.local/api",
                    "scopes": ["write:firewall:fw-sample"],
                    "expires_at": "2026-05-06T20:00:00Z",
                },
            },
        )

    client = TestClient(
        create_app(
            ChainlitMiddlewareSettings(
                ag_ui_gateway_url="http://ag-ui.test/agent",
                agent_service_url="http://agent-service.test",
            ),
            http_client_factory=_mock_client_factory(httpx.MockTransport(handler)),
        )
    )

    response = client.post(
        "/chainlit/events/approve",
        json={"workflow_id": "wf-hitl", "plan_hash": "sha256:hitl"},
    )

    assert response.status_code == 200
    assert captured["url"] == "http://agent-service.test/workflows/wf-hitl/approve"
    assert captured["payload"] == {
        "approved": True,
        "approved_by_user_id": "chainlit-placeholder-user",
        "plan_hash": "sha256:hitl",
    }
    assert response.json()["token_exchange"]["attempted"] is True
    assert response.json()["workflow"]["status"] == "completed"


def _mock_client_factory(transport: httpx.MockTransport):
    @asynccontextmanager
    async def client() -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(transport=transport) as async_client:
            yield async_client

    return client


def _json_request(request: httpx.Request) -> Any:
    return json.loads(request.read())

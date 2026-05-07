from __future__ import annotations

import json
from typing import Any  # noqa: UP035

from ag_ui_gateway.app import create_app
from fastapi.testclient import TestClient


class FakeAgentServiceClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    async def plan_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(payload)
        return {
            "workflow_id": "wf-1",
            "status": {"status": "awaiting_approval"},
            "plan": {
                "workflow_id": "wf-1",
                "user_id": payload["user_id"],
                "session_id": payload["session_id"],
                "tenant_id": payload["tenant_id"],
                "steps": [
                    {
                        "step_id": "step-1",
                        "target_agent": "developer",
                        "action": "get_developer_app",
                        "arguments": {"appid": "sample-app"},
                        "required_scopes": ["read:client:sample-app"],
                        "hitl": {"description": "Approve developer app lookup"},
                    }
                ],
            },
            "plan_hash": "hash-1",
            "authorization": {"workflow_id": "wf-1", "scopes": ["read:client:sample-app"]},
            "approved_workflow": None,
            "events": [
                {
                    "event_type": "workflow.planned",
                    "message": "Supervisor planned a workflow manifest from subagent proposals.",
                    "attributes": {"proposal_count": 1},
                },
                {
                    "event_type": "workflow.awaiting_approval",
                    "message": "Workflow manifest is awaiting human approval.",
                    "attributes": {"required_scopes": ["read:client:sample-app"]},
                },
            ],
            "step_results": [],
        }


def test_capabilities_response() -> None:
    client = TestClient(create_app(agent_service=FakeAgentServiceClient()))

    response = client.get("/agent/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "service": "ag-ui-gateway",
        "protocol": "ag-ui",
        "endpoints": ["GET /healthz", "GET /agent/capabilities", "POST /agent"],
        "input_schema": {
            "threadId": "string",
            "runId": "string",
            "messages": "array",
            "state": "object",
        },
        "event_types": [
            "RUN_STARTED",
            "TEXT_MESSAGE_CONTENT",
            "STATE_DELTA",
            "CUSTOM",
            "RUN_FINISHED",
        ],
    }


def test_agent_post_streams_lifecycle_text_state_hitl_and_finish() -> None:
    service = FakeAgentServiceClient()
    client = TestClient(create_app(agent_service=service))

    with client.stream(
        "POST",
        "/agent",
        json={
            "threadId": "thread-1",
            "runId": "run-1",
            "messages": [{"role": "user", "content": "Check app sample-app"}],
            "state": {
                "user_id": "user-1",
                "session_id": "session-1",
                "tenant_id": "tenant-1",
                "token_ref": "token:1",
                "token_scopes": ["read:clients"],
                "allowed_tools": ["get_developer_app"],
            },
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(response.read().decode())

    assert [event["event"] for event in events] == [
        "RUN_STARTED",
        "TEXT_MESSAGE_CONTENT",
        "STATE_DELTA",
        "CUSTOM",
        "RUN_FINISHED",
    ]
    assert events[0]["data"]["runId"] == "run-1"
    assert (
        events[1]["data"]["delta"]
        == "Workflow wf-1 is awaiting_approval with 1 planned step(s)."
    )
    assert events[2]["data"]["delta"]["workflow"]["workflow_id"] == "wf-1"
    assert events[3]["data"]["name"] == "hitl.approval.requested"
    assert events[3]["data"]["value"] == {
        "kind": "HITL_APPROVAL",
        "workflow_id": "wf-1",
        "plan_hash": "hash-1",
        "required_scopes": ["read:client:sample-app"],
        "message": "Workflow manifest is awaiting human approval.",
    }
    assert events[4]["data"]["type"] == "RUN_FINISHED"
    assert service.requests == [
        {
            "question": "Check app sample-app",
            "user_id": "user-1",
            "session_id": "session-1",
            "tenant_id": "tenant-1",
            "auth_context_ref": None,
            "token_ref": "token:1",
            "token_scopes": ["read:clients"],
            "allowed_tools": ["get_developer_app"],
        }
    ]


def _parse_sse(body: str) -> list[dict[str, Any]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append({"event": event, "data": data})
    return events

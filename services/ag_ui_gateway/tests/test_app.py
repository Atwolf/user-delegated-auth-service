from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast  # noqa: UP035

import pytest
from ag_ui_gateway.app import create_app
from fastapi.testclient import TestClient
from session_state import TrustedSessionContext, signed_session_context_headers


@pytest.fixture(autouse=True)
def internal_auth_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_AUTH_SECRET", "test-internal-secret")


class FakeAgentServiceClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.headers: list[dict[str, str] | None] = []

    async def stream_run(
        self,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> Any:
        self.requests.append(payload)
        self.headers.append(headers)
        workflow = {
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
                        "input_payload_json": '{"appid":"sample-app"}',
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
            "step_results": [
                {
                    "step_id": "step-1",
                    "target_agent": "developer",
                    "action": "get_developer_app",
                    "status": "completed",
                    "output": {"appid": "sample-app"},
                }
            ],
        }
        message_id = f"{payload['run_id']}:assistant"
        tool_call_id = f"{payload['run_id']}:step-1"
        yield {"type": "RUN_STARTED", "threadId": payload["thread_id"], "runId": payload["run_id"]}
        yield {"type": "TEXT_MESSAGE_START", "messageId": message_id, "role": "assistant"}
        yield {
            "type": "TEXT_MESSAGE_CONTENT",
            "messageId": message_id,
            "delta": "Agent runtime planned a developer app lookup.",
        }
        yield {"type": "TEXT_MESSAGE_END", "messageId": message_id}
        yield {
            "type": "STATE_DELTA",
            "delta": [{"op": "add", "path": "/workflow", "value": workflow}],
        }
        yield {
            "type": "TOOL_CALL_START",
            "toolCallId": tool_call_id,
            "toolCallName": "get_developer_app",
            "parentMessageId": message_id,
        }
        yield {
            "type": "TOOL_CALL_ARGS",
            "toolCallId": tool_call_id,
            "delta": '{"appid":"sample-app"}',
        }
        yield {"type": "TOOL_CALL_END", "toolCallId": tool_call_id}
        yield {
            "type": "TOOL_CALL_RESULT",
            "messageId": message_id,
            "toolCallId": tool_call_id,
            "content": json.dumps(
                {
                    "step_id": "step-1",
                    "target_agent": "developer",
                    "action": "get_developer_app",
                    "status": "completed",
                    "output": {"appid": "sample-app"},
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            "role": "tool",
        }
        yield {
            "type": "CUSTOM",
            "name": "hitl.approval.requested",
            "value": {
                "kind": "HITL_APPROVAL",
                "workflow_id": "wf-1",
                "plan_hash": "hash-1",
                "required_scopes": ["read:client:sample-app"],
                "message": "Workflow manifest is awaiting human approval.",
            },
        }
        yield {"type": "RUN_FINISHED", "threadId": payload["thread_id"], "runId": payload["run_id"]}


class FailingAgentServiceClient:
    async def stream_run(
        self,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> Any:
        _ = payload, headers
        raise RuntimeError("planning exploded")
        yield {}


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
            "TEXT_MESSAGE_START",
            "TEXT_MESSAGE_CONTENT",
            "TEXT_MESSAGE_END",
            "STATE_DELTA",
            "TOOL_CALL_START",
            "TOOL_CALL_ARGS",
            "TOOL_CALL_END",
            "TOOL_CALL_RESULT",
            "CUSTOM",
            "RUN_FINISHED",
            "RUN_ERROR",
        ],
    }


def test_agent_post_streams_ag_ui_events_in_order() -> None:
    service = FakeAgentServiceClient()
    raw_body, events = _post_agent(service)

    assert "event:" not in raw_body
    assert [event["type"] for event in events] == [
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "STATE_DELTA",
        "TOOL_CALL_START",
        "TOOL_CALL_ARGS",
        "TOOL_CALL_END",
        "TOOL_CALL_RESULT",
        "CUSTOM",
        "RUN_FINISHED",
    ]
    assert service.requests == [
        {
            "question": "Check app sample-app",
            "messages": [{"role": "user", "content": "Check app sample-app"}],
            "state": {
                "public_hint": "safe",
            },
            "user_id": "user-1",
            "session_id": "session-1",
            "tenant_id": "tenant-1",
            "token_ref": "token:1",
            "token_scopes": ["read:clients"],
            "allowed_tools": ["get_developer_app"],
            "thread_id": "thread-1",
            "run_id": "run-1",
        }
    ]
    assert "threadId" not in service.requests[0]
    assert "runId" not in service.requests[0]
    assert "correlation_id" not in service.requests[0]
    assert "expires_at" not in service.requests[0]
    assert service.headers[0] is not None
    assert "x-magnum-session-context" in service.headers[0]
    assert "x-magnum-session-signature" in service.headers[0]


def test_text_and_tool_events_share_stable_ids() -> None:
    _, events = _post_agent(FakeAgentServiceClient())

    assert events[1] == {
        "type": "TEXT_MESSAGE_START",
        "messageId": "run-1:assistant",
        "role": "assistant",
    }
    assert events[2]["messageId"] == "run-1:assistant"
    assert events[3] == {"type": "TEXT_MESSAGE_END", "messageId": "run-1:assistant"}
    assert events[2]["delta"] == "Agent runtime planned a developer app lookup."

    tool_events = events[5:9]
    assert {event["toolCallId"] for event in tool_events} == {"run-1:step-1"}
    assert tool_events[0] == {
        "type": "TOOL_CALL_START",
        "toolCallId": "run-1:step-1",
        "toolCallName": "get_developer_app",
        "parentMessageId": "run-1:assistant",
    }
    assert json.loads(tool_events[1]["delta"]) == {"appid": "sample-app"}
    assert json.loads(tool_events[3]["content"]) == {
        "step_id": "step-1",
        "target_agent": "developer",
        "action": "get_developer_app",
        "status": "completed",
        "output": {"appid": "sample-app"},
    }


def test_state_delta_uses_json_patch_shape() -> None:
    _, events = _post_agent(FakeAgentServiceClient())

    state_delta = events[4]
    assert state_delta["type"] == "STATE_DELTA"
    assert state_delta["delta"] == [
        {
            "op": "add",
            "path": "/workflow",
            "value": {
                "workflow_id": "wf-1",
                "status": {"status": "awaiting_approval"},
                "plan": {
                    "workflow_id": "wf-1",
                    "steps": [
                        {
                            "step_id": "step-1",
                            "target_agent": "developer",
                            "action": "get_developer_app",
                            "input_payload_json": '{"appid":"sample-app"}',
                            "required_scopes": ["read:client:sample-app"],
                            "hitl": {"description": "Approve developer app lookup"},
                        }
                    ],
                },
                "plan_hash": "hash-1",
                "approved_workflow": None,
                "events": [
                    {
                        "event_type": "workflow.planned",
                        "message": (
                            "Supervisor planned a workflow manifest from subagent proposals."
                        ),
                        "attributes": {"proposal_count": 1},
                    },
                    {
                        "event_type": "workflow.awaiting_approval",
                        "message": "Workflow manifest is awaiting human approval.",
                        "attributes": {"required_scopes": ["read:client:sample-app"]},
                    },
                ],
                "step_results": [
                    {
                        "step_id": "step-1",
                        "target_agent": "developer",
                        "action": "get_developer_app",
                        "status": "completed",
                        "output": {"appid": "sample-app"},
                    }
                ],
            },
        }
    ]


def test_hitl_custom_event_and_finish_are_emitted() -> None:
    _, events = _post_agent(FakeAgentServiceClient())

    assert events[9] == {
        "type": "CUSTOM",
        "name": "hitl.approval.requested",
        "value": {
            "kind": "HITL_APPROVAL",
            "workflow_id": "wf-1",
            "plan_hash": "hash-1",
            "required_scopes": ["read:client:sample-app"],
            "message": "Workflow manifest is awaiting human approval.",
        },
    }
    assert events[10] == {
        "type": "RUN_FINISHED",
        "threadId": "thread-1",
        "runId": "run-1",
    }


def test_agent_post_emits_run_error_on_exception() -> None:
    raw_body, events = _post_agent(FailingAgentServiceClient())

    assert "event:" not in raw_body
    assert events == [
        {"type": "RUN_STARTED", "threadId": "thread-1", "runId": "run-1"},
        {
            "type": "RUN_ERROR",
            "message": "planning exploded",
            "code": "AGENT_SERVICE_ERROR",
        },
    ]


def test_agent_post_rejects_missing_signed_session_context() -> None:
    client = TestClient(create_app(agent_service=FakeAgentServiceClient()))

    with client.stream(
        "POST",
        "/agent",
        json={
            "threadId": "thread-1",
            "runId": "run-1",
            "messages": [{"role": "user", "content": "Check app sample-app"}],
            "state": {"user_id": "attacker"},
        },
    ) as response:
        assert response.status_code == 401


def test_agent_post_ignores_forged_state_identity() -> None:
    service = FakeAgentServiceClient()
    raw_body, events = _post_agent(service)

    assert events[0]["type"] == "RUN_STARTED"
    request = service.requests[0]
    assert request["user_id"] == "user-1"
    assert request["session_id"] == "session-1"
    assert request["tenant_id"] == "tenant-1"
    assert request["token_ref"] == "token:1"
    assert request["token_scopes"] == ["read:clients"]
    assert request["allowed_tools"] == ["get_developer_app"]
    assert request["state"] == {"public_hint": "safe"}
    assert "attacker" not in raw_body
    assert "session-1" not in raw_body
    assert "tenant-1" not in raw_body
    assert "token:1" not in raw_body
    assert "user-1" not in raw_body


def _post_agent(agent_service: Any) -> tuple[str, list[dict[str, Any]]]:
    client = TestClient(create_app(agent_service=agent_service))

    with client.stream(
        "POST",
        "/agent",
        headers=_signed_context_headers(),
        json={
            "threadId": "thread-1",
            "runId": "run-1",
            "messages": [{"role": "user", "content": "Check app sample-app"}],
            "state": {
                "allowed_tools": ["restart_vm"],
                "public_hint": "safe",
                "session_id": "attacker-session",
                "tenant_id": "attacker-tenant",
                "token_ref": "token:attacker",
                "token_scopes": ["admin:*"],
                "user_id": "attacker",
            },
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw_body = response.read().decode()
    return raw_body, _parse_sse_data_events(raw_body)


def _signed_context_headers() -> dict[str, str]:
    return signed_session_context_headers(
        TrustedSessionContext(
            allowed_tools=["get_developer_app"],
            correlation_id="run-1",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            session_id="session-1",
            tenant_id="tenant-1",
            token_ref="token:1",
            token_scopes=["read:clients"],
            user_id="user-1",
        ),
        secret="test-internal-secret",
    )


def _parse_sse_data_events(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        assert lines
        assert all(line.startswith("data: ") for line in lines)
        data = "\n".join(line.removeprefix("data: ") for line in lines)
        decoded: object = json.loads(data)
        assert isinstance(decoded, dict)
        event = cast(dict[str, Any], decoded)
        assert isinstance(event.get("type"), str)
        events.append(event)
    return events

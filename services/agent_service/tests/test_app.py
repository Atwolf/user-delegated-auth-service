from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

os.environ.setdefault("AGENT_SERVICE_STATE_BACKEND", "memory")
os.environ.setdefault("AGENT_SERVICE_ENABLE_TEST_MEMORY_STATE", "true")

from agent_service.app import create_app
from agent_service.models import PlanWorkflowRequest, SanitizedWorkflowContext, TokenRegistryRecord
from agent_service.orchestration import ToolIntentDispatcher
from agent_service.providers import (
    AdkRuntimeTypes,
    AgentRuntimeResult,
    GoogleAdkToolIntentProvider,
)
from agent_service.state import InMemoryAgentServiceStore, RedisAgentServiceStore
from fastapi.testclient import TestClient
from session_state import TrustedSessionContext, signed_session_context_headers
from token_broker import WorkflowTokenExchangeResponse
from workflow_core import ExecutionGrant, ToolIntent, verify_execution_grant

agent_app = importlib.import_module("agent_service.app")


class FakeIntentProvider:
    def __init__(self, intents: list[ToolIntent]) -> None:
        self.intents = intents

    async def propose(
        self,
        context: SanitizedWorkflowContext,
        *,
        allowed_tool_names: set[str] | None,
        available_tool_names: set[str],
    ) -> list[ToolIntent]:
        return self.intents


class FakeRuntimeProvider(FakeIntentProvider):
    async def run(
        self,
        context: SanitizedWorkflowContext,
        *,
        allowed_tool_names: set[str] | None,
        available_tool_names: set[str],
    ) -> AgentRuntimeResult:
        _ = context, allowed_tool_names, available_tool_names
        return AgentRuntimeResult(
            assistant_message="Agent Runtime selected a DNS inspection.",
            tool_intents=self.intents,
        )


class SensitiveEchoRuntimeProvider(FakeIntentProvider):
    async def run(
        self,
        context: SanitizedWorkflowContext,
        *,
        allowed_tool_names: set[str] | None,
        available_tool_names: set[str],
    ) -> AgentRuntimeResult:
        _ = allowed_tool_names, available_tool_names
        token_ref = context.token_ref or "missing-token-ref"
        return AgentRuntimeResult(
            assistant_message=f"Echoing {token_ref} would leak a token reference.",
            tool_intents=[
                _intent(
                    "inspect_dns_record",
                    {"record_name": token_ref},
                    reason=f"Inspect record derived from {token_ref}.",
                )
            ],
        )


class SlowRuntimeProvider(FakeIntentProvider):
    async def run(
        self,
        context: SanitizedWorkflowContext,
        *,
        allowed_tool_names: set[str] | None,
        available_tool_names: set[str],
    ) -> AgentRuntimeResult:
        _ = context, allowed_tool_names, available_tool_names
        await asyncio.sleep(1)
        return AgentRuntimeResult(assistant_message="Too late.", tool_intents=[])


def _intent(
    tool_name: str,
    arguments: dict[str, object],
    *,
    agent_name: str = "google_adk_coordinator",
    reason: str = "Agent Runtime selected this tool.",
) -> ToolIntent:
    return ToolIntent(
        agent_name=agent_name,
        mcp_server="agent-runtime",
        tool_name=tool_name,
        arguments=arguments,
        reason=reason,
        metadata_ref=f"google_adk:{tool_name}",
    )


def _client_with_intents(intents: list[ToolIntent]) -> TestClient:
    return _client(create_app(intent_provider=FakeIntentProvider(intents)))


def _client(
    app: Any,
    *,
    allowed_tools: list[str] | None = None,
    user_id: str = "user-1",
    session_id: str = "session-1",
    tenant_id: str | None = None,
) -> TestClient:
    return TestClient(
        app,
        headers=_signed_context_headers(
            allowed_tools=allowed_tools,
            user_id=user_id,
            session_id=session_id,
            tenant_id=tenant_id,
        ),
    )


def _signed_context_headers(
    *,
    user_id: str = "user-1",
    session_id: str = "session-1",
    tenant_id: str | None = None,
    token_ref: str | None = "auth0:sample",
    token_scopes: list[str] | None = None,
    allowed_tools: list[str] | None = None,
) -> dict[str, str]:
    return signed_session_context_headers(
        TrustedSessionContext(
            allowed_tools=allowed_tools,
            correlation_id="test-run",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            session_id=session_id,
            tenant_id=tenant_id,
            token_ref=token_ref,
            token_scopes=token_scopes
            or [
                "admin:cloud",
                "admin:iam",
                "admin:network",
                "admin:vpn",
                "read:cloud",
                "read:dns",
                "read:network",
                "read:vm",
                "read:workflow",
                "write:cloud",
                "write:vm",
            ],
            user_id=user_id,
        ),
        secret="test-internal-secret",
    )


@pytest.fixture(autouse=True)
def internal_auth_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_AUTH_SECRET", "test-internal-secret")


def test_agent_listing_includes_worker_c_subagents() -> None:
    client = _client(create_app())

    response = client.get("/agents")

    assert response.status_code == 200
    names = [agent["name"] for agent in response.json()["agents"]]
    assert names == ["google_adk_coordinator"]


def test_plan_workflow_returns_network_intent() -> None:
    client = _client_with_intents(
        [
            _intent("rotate_vpn_credential", {"credential_id": "vpn-sample"}),
            _intent("inspect_dns_record", {"record_name": "app.example.com"}),
        ]
    )

    response = client.post(
        "/workflows/plan",
        json={
            "query": "Check VPN and DNS health for the branch network",
            "user_id": "user-1",
            "session_id": "session-1",
            "token_ref": "auth0:sample",
            "token_scopes": ["read:workflow"],
        },
    )

    assert response.status_code == 200
    workflow = response.json()["workflow"]
    assert "auth_context_ref" not in workflow
    tool_names = [intent["tool_name"] for intent in workflow["tool_intents"]]
    assert "rotate_vpn_credential" in tool_names
    assert "inspect_dns_record" in tool_names
    assert workflow["status"] == "awaiting_approval"
    assert workflow["policy"]["requires_hitl"] is True
    operations = [step["operation_type"] for step in workflow["proposal"]["steps"]]
    assert "READ" in operations
    assert "ADMIN" in operations


def test_plan_workflow_returns_cloud_intent() -> None:
    client = _client_with_intents(
        [
            _intent("inspect_vm", {"vm_id": "vm-sample"}),
            _intent(
                "update_iam_binding",
                {"principal_id": "user-sample", "role": "roles/viewer"},
            ),
        ]
    )

    response = client.post(
        "/workflows/plan",
        json={
            "query": "Review VM and IAM posture in the cloud project",
            "user_id": "user-1",
            "session_id": "session-1",
            "allowed_tools": ["inspect_vm", "update_iam_binding"],
        },
    )

    assert response.status_code == 200
    workflow = response.json()["workflow"]
    tool_names = [intent["tool_name"] for intent in workflow["tool_intents"]]
    assert "inspect_vm" in tool_names
    assert "update_iam_binding" in tool_names
    assert workflow["policy"]["blast_radius"] == "high"


def test_plan_workflow_maps_explicit_restart_to_hitl_restart_vm() -> None:
    client = _client_with_intents([_intent("restart_vm", {"vm_id": "vm-sample"})])

    response = client.post(
        "/workflows/plan",
        json={
            "query": "Restart vm-sample now",
            "user_id": "user-1",
            "session_id": "session-1",
            "allowed_tools": ["restart_vm"],
            "token_scopes": ["write:vm"],
        },
    )

    assert response.status_code == 200
    workflow = response.json()["workflow"]
    assert workflow["status"] == "awaiting_approval"
    assert workflow["policy"]["requires_hitl"] is True
    assert workflow["policy"]["blast_radius"] == "medium"
    assert workflow["tool_intents"][0]["tool_name"] == "restart_vm"
    assert workflow["proposal"]["steps"][0]["action"] == "restart_vm"
    assert workflow["proposal"]["steps"][0]["operation_type"] == "WRITE"


def test_plan_workflow_does_not_add_default_tool_intent() -> None:
    client = _client_with_intents([])

    response = client.post(
        "/workflows/plan",
        json={
            "query": "What can you help me understand today?",
            "user_id": "user-1",
            "session_id": "session-1",
        },
    )

    assert response.status_code == 200
    workflow = response.json()["workflow"]
    assert workflow["tool_intents"] == []
    assert workflow["status"] == "ready"
    assert workflow["proposal"]["steps"] == []


def test_token_context_registers_auth_context_without_returning_it() -> None:
    store = InMemoryAgentServiceStore()
    client = _client(
        create_app(
            store=store,
            intent_provider=FakeIntentProvider(
                [_intent("inspect_dns_record", {"record_name": "app.example.com"})]
            ),
        )
    )

    response = client.post(
        "/token-context",
        json={
            "auth_context_ref": "raw-auth-token",
            "user_id": "user-1",
            "session_id": "session-1",
            "token_ref": "auth0:sample",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"token_ref": "auth0:sample"}
    assert (
        asyncio.run(
            store.get_auth_context(
                user_id="user-1",
                session_id="session-1",
                token_ref="auth0:sample",
            )
        )
        == "raw-auth-token"
    )


def test_run_stream_reaches_agent_runtime_and_emits_ag_ui_events() -> None:
    store = InMemoryAgentServiceStore()
    client = _client(
        create_app(
            store=store,
            intent_provider=FakeRuntimeProvider(
                [_intent("inspect_dns_record", {"record_name": "app.example.com"})]
            )
        )
    )

    with client.stream(
        "POST",
        "/runs/stream",
        json={
            "query": "Check DNS health for app.example.com",
            "threadId": "thread-1",
            "runId": "run-1",
            "user_id": "user-1",
            "session_id": "session-1",
            "allowed_tools": ["inspect_dns_record"],
            "messages": [
                {"id": "msg-user-1", "role": "user", "content": "Inspect VM vm-sample"},
                {
                    "id": "msg-assistant-1",
                    "role": "assistant",
                    "content": "Inspecting VM vm-sample now.",
                    "toolCalls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "inspect_vm",
                                "arguments": "{\"vm_id\":\"vm-sample\"}",
                            },
                        }
                    ],
                },
                {
                    "id": "tool-1",
                    "role": "tool",
                    "toolCallId": "call-1",
                    "content": "{\"status\":\"planned\"}",
                },
                {
                    "id": "msg-user-2",
                    "role": "user",
                    "content": "Check DNS health for app.example.com",
                },
            ],
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode()

    events = _parse_sse_data_events(body)
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
        "RUN_FINISHED",
    ]
    assert events[2]["delta"] == "Agent Runtime selected a DNS inspection."
    assert events[5]["toolCallName"] == "inspect_dns_record"
    state_delta = events[4]["delta"][0]["value"]
    assert "user_id" not in json.dumps(state_delta)
    assert "session_id" not in json.dumps(state_delta)
    assert "tenant_id" not in json.dumps(state_delta)
    assert "token_ref" not in json.dumps(state_delta)
    assert "auth_context_ref" not in json.dumps(state_delta)

    thread = asyncio.run(
        store.get_thread(thread_id="thread-1", user_id="user-1", session_id="session-1")
    )
    assert thread is not None
    assert [message["role"] for message in thread.messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    restored_prior_tool = thread.messages[1]["content"][1]
    assert restored_prior_tool["type"] == "tool-call"
    assert restored_prior_tool["toolName"] == "inspect_vm"
    assert restored_prior_tool["result"] == {"status": "planned"}
    restored_latest = thread.messages[-1]
    assert restored_latest["content"][0]["text"] == "Agent Runtime selected a DNS inspection."
    assert restored_latest["content"][1]["toolName"] == "inspect_dns_record"
    assert restored_latest["content"][1]["result"]["status"] == "planned"


def test_run_stream_times_out_slow_agent_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_TIMEOUT_SECONDS", "0.01")
    client = _client(
        create_app(
            store=InMemoryAgentServiceStore(),
            intent_provider=SlowRuntimeProvider([]),
        )
    )

    with client.stream(
        "POST",
        "/runs/stream",
        json={
            "query": "Check DNS health",
            "threadId": "thread-timeout-1",
            "runId": "run-timeout-1",
            "user_id": "user-1",
            "session_id": "session-1",
            "allowed_tools": ["inspect_dns_record"],
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode()

    events = _parse_sse_data_events(body)
    assert events == [
        {"type": "RUN_STARTED", "threadId": "thread-timeout-1", "runId": "run-timeout-1"},
        {
            "type": "RUN_ERROR",
            "message": "TimeoutError",
            "code": "AGENT_RUNTIME_ERROR",
        },
    ]


def test_run_stream_redacts_token_ref_from_browser_visible_strings() -> None:
    store = InMemoryAgentServiceStore()
    client = _client(
        create_app(store=store, intent_provider=SensitiveEchoRuntimeProvider([])),
        allowed_tools=["inspect_dns_record"],
    )

    with client.stream(
        "POST",
        "/runs/stream",
        json={
            "query": "Check DNS health for auth0:sample",
            "threadId": "thread-sensitive-1",
            "runId": "run-sensitive-1",
            "user_id": "user-1",
            "session_id": "session-1",
            "allowed_tools": ["inspect_dns_record"],
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode()

    assert "auth0:sample" not in body
    assert "[REDACTED]" in body
    events = _parse_sse_data_events(body)
    assert events[2]["delta"] == "Echoing [REDACTED] would leak a token reference."
    assert events[5]["toolCallName"] == "inspect_dns_record"
    assert '"record_name":"[REDACTED]"' in events[6]["delta"]

    thread = asyncio.run(
        store.get_thread(
            thread_id="thread-sensitive-1",
            user_id="user-1",
            session_id="session-1",
        )
    )
    assert thread is not None
    assert "auth0:sample" not in json.dumps(thread.messages)


def test_workflow_restore_and_cancel_approval_are_scoped_to_user_session() -> None:
    app = create_app(
        intent_provider=FakeIntentProvider(
            [_intent("inspect_dns_record", {"record_name": "app.example.com"})]
        )
    )
    client = _client(app)
    plan_response = client.post(
        "/workflows/plan",
        json={
            "query": "Check DNS health for app.example.com",
            "user_id": "user-1",
            "session_id": "session-1",
            "threadId": "thread-approval-1",
        },
    )
    workflow = plan_response.json()["workflow"]
    assert workflow["thread_id"] == "thread-approval-1"

    wrong_session_response = _client(app, session_id="session-2").get(
        f"/workflows/{workflow['workflow_id']}"
    )
    assert wrong_session_response.status_code == 404

    restore_response = client.get(
        f"/workflows/{workflow['workflow_id']}",
        params={"user_id": "user-1", "session_id": "session-1"},
    )
    assert restore_response.status_code == 200

    cancel_response = client.post(
        f"/workflows/{workflow['workflow_id']}/approve",
        json={
            "approved": False,
            "user_id": "user-1",
            "session_id": "session-1",
            "approved_by_user_id": "user-1",
            "plan_hash": workflow["plan_hash"],
        },
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["workflow"]["status"] == "cancelled"
    restored_thread = client.get(
        "/threads/thread-approval-1",
        params={"user_id": "user-1", "session_id": "session-1"},
    )
    assert restored_thread.status_code == 200
    assert restored_thread.json()["thread"]["state"]["workflow"]["status"] == "cancelled"

    repeat_response = client.post(
        f"/workflows/{workflow['workflow_id']}/approve",
        json={
            "approved": True,
            "user_id": "user-1",
            "session_id": "session-1",
            "approved_by_user_id": "user-1",
            "plan_hash": workflow["plan_hash"],
        },
    )
    assert repeat_response.status_code == 200
    assert repeat_response.json()["workflow"]["status"] == "cancelled"
    assert repeat_response.json()["token_exchange"] == {
        "attempted": False,
        "reason": "workflow already cancelled",
    }


def test_workflow_access_is_tenant_scoped() -> None:
    app = create_app(
        intent_provider=FakeIntentProvider(
            [_intent("inspect_dns_record", {"record_name": "app.example.com"})]
        )
    )
    tenant_a = _client(app, tenant_id="tenant-a")
    workflow = tenant_a.post(
        "/workflows/plan",
        json={
            "query": "Check DNS health for app.example.com",
            "session_id": "session-1",
            "user_id": "user-1",
        },
    ).json()["workflow"]

    assert workflow["tenant_id"] == "tenant-a"
    assert _client(app, tenant_id="tenant-b").get(
        f"/workflows/{workflow['workflow_id']}"
    ).status_code == 404
    assert _client(app, tenant_id="tenant-b").post(
        f"/workflows/{workflow['workflow_id']}/approve",
        json={"approved": False, "plan_hash": workflow["plan_hash"]},
    ).status_code == 404


def test_approval_rejects_cross_user_session_context() -> None:
    app = create_app(
        intent_provider=FakeIntentProvider(
            [_intent("inspect_dns_record", {"record_name": "app.example.com"})]
        )
    )
    client = _client(app)
    plan_response = client.post(
        "/workflows/plan",
        json={
            "query": "Check DNS health for app.example.com",
            "user_id": "user-1",
            "session_id": "session-1",
        },
    )
    workflow = plan_response.json()["workflow"]

    response = _client(app, user_id="user-2").post(
        f"/workflows/{workflow['workflow_id']}/approve",
        json={
            "approved": False,
            "user_id": "user-1",
            "session_id": "session-1",
            "approved_by_user_id": "user-2",
            "plan_hash": workflow["plan_hash"],
        },
    )

    assert response.status_code == 404


def test_approval_rejects_stale_plan_hash() -> None:
    app = create_app(
        intent_provider=FakeIntentProvider(
            [_intent("inspect_dns_record", {"record_name": "app.example.com"})]
        )
    )
    client = _client(app)
    workflow = client.post(
        "/workflows/plan",
        json={
            "query": "Check DNS health for app.example.com",
            "session_id": "session-1",
            "user_id": "user-1",
        },
    ).json()["workflow"]

    response = client.post(
        f"/workflows/{workflow['workflow_id']}/approve",
        json={"approved": True, "plan_hash": "sha256:stale"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "plan_hash does not match workflow manifest"}


def test_approval_executes_with_signed_execution_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    store = InMemoryAgentServiceStore()
    egress = RecordingEgressClient()
    monkeypatch.setattr(agent_app.httpx, "AsyncClient", egress.client_factory)
    monkeypatch.setattr(agent_app, "_exchange_obo_token", _fake_obo_exchange)
    app = create_app(
        store=store,
        intent_provider=FakeIntentProvider([_intent("restart_vm", {"vm_id": "vm-sample"})]),
    )
    client = _client(app, allowed_tools=["restart_vm"])

    client.post(
        "/token-context",
        json={"auth_context_ref": "raw-auth-token", "token_ref": "auth0:sample"},
    )
    workflow = client.post(
        "/workflows/plan",
        json={
            "allowed_tools": ["restart_vm"],
            "query": "Restart vm-sample",
            "session_id": "session-1",
            "token_scopes": ["write:vm"],
            "user_id": "user-1",
        },
    ).json()["workflow"]

    response = client.post(
        f"/workflows/{workflow['workflow_id']}/approve",
        json={"approved": True, "plan_hash": workflow["plan_hash"]},
    )

    assert response.status_code == 200
    approval_payload = response.json()
    assert approval_payload["workflow"]["status"] == "completed"
    assert "access_token" not in json.dumps(approval_payload)
    assert "obo:" not in json.dumps(approval_payload)
    assert "obo_token_ref" not in json.dumps(approval_payload)
    restored = client.get(f"/workflows/{workflow['workflow_id']}").json()["workflow"]
    assert restored["egress_results"][0]["tool_name"] == "restart_vm"
    assert "obo:" not in json.dumps(restored)
    assert "obo_token_ref" not in json.dumps(restored)
    assert len(egress.requests) == 1
    outbound = egress.requests[0]
    grant = ExecutionGrant.model_validate(outbound["execution_grant"])
    verify_execution_grant(
        grant,
        signature=outbound["execution_grant_signature"],
        secret="test-internal-secret",
    )
    assert grant.workflow_id == workflow["workflow_id"]
    assert grant.approval_id == outbound["approval_id"]
    assert grant.tool_name == "restart_vm"
    assert grant.arguments == {"vm_id": "vm-sample"}
    assert outbound["access_token"] == "obo-access-token"
    assert outbound["token_audience"] == "https://api.example.test"
    assert set(grant.required_scopes).issubset(set(outbound["token_scopes"]))


def test_approval_marks_workflow_failed_when_egress_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryAgentServiceStore()
    egress = RecordingEgressClient(mcp_status="failed")
    monkeypatch.setattr(agent_app.httpx, "AsyncClient", egress.client_factory)
    monkeypatch.setattr(agent_app, "_exchange_obo_token", _fake_obo_exchange)
    app = create_app(
        store=store,
        intent_provider=FakeIntentProvider([_intent("restart_vm", {"vm_id": "vm-sample"})]),
    )
    client = _client(app, allowed_tools=["restart_vm"])

    client.post(
        "/token-context",
        json={"auth_context_ref": "raw-auth-token", "token_ref": "auth0:sample"},
    )
    workflow = client.post(
        "/workflows/plan",
        json={
            "allowed_tools": ["restart_vm"],
            "query": "Restart vm-sample",
            "session_id": "session-1",
            "token_scopes": ["write:vm"],
            "user_id": "user-1",
        },
    ).json()["workflow"]

    response = client.post(
        f"/workflows/{workflow['workflow_id']}/approve",
        json={"approved": True, "plan_hash": workflow["plan_hash"]},
    )

    assert response.status_code == 502
    restored = client.get(f"/workflows/{workflow['workflow_id']}").json()["workflow"]
    assert restored["status"] == "failed"
    assert restored["egress_results"][0]["status"] == "failed"
    assert restored["egress_results"][0]["message"] == (
        "egress gateway reported failed MCP execution"
    )


def test_approval_marks_workflow_failed_when_obo_audience_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryAgentServiceStore()
    egress = RecordingEgressClient()
    monkeypatch.setattr(agent_app.httpx, "AsyncClient", egress.client_factory)
    monkeypatch.setattr(agent_app, "_exchange_obo_token", _fake_obo_exchange_without_audience)
    app = create_app(
        store=store,
        intent_provider=FakeIntentProvider([_intent("restart_vm", {"vm_id": "vm-sample"})]),
    )
    client = _client(app, allowed_tools=["restart_vm"])
    client.post(
        "/token-context",
        json={"auth_context_ref": "raw-auth-token", "token_ref": "auth0:sample"},
    )
    workflow = client.post(
        "/workflows/plan",
        json={"query": "Restart vm-sample", "session_id": "session-1", "user_id": "user-1"},
    ).json()["workflow"]

    response = client.post(
        f"/workflows/{workflow['workflow_id']}/approve",
        json={"approved": True, "plan_hash": workflow["plan_hash"]},
    )

    assert response.status_code == 502
    assert not egress.requests
    restored = client.get(f"/workflows/{workflow['workflow_id']}").json()["workflow"]
    assert restored["status"] == "failed"
    assert restored["egress_results"][0]["message"] == "obo token audience is required"


def test_repeat_approval_while_executing_does_not_dispatch_again() -> None:
    store = InMemoryAgentServiceStore()
    app = create_app(
        store=store,
        intent_provider=FakeIntentProvider([_intent("restart_vm", {"vm_id": "vm-sample"})]),
    )
    client = _client(app, allowed_tools=["restart_vm"])
    workflow = client.post(
        "/workflows/plan",
        json={"query": "Restart vm-sample", "session_id": "session-1", "user_id": "user-1"},
    ).json()["workflow"]
    existing = asyncio.run(
        store.get_workflow(
            workflow_id=workflow["workflow_id"],
            session_id="session-1",
            user_id="user-1",
        )
    )
    assert existing is not None
    asyncio.run(store.save_workflow(existing.model_copy(update={"status": "executing"})))

    response = client.post(
        f"/workflows/{workflow['workflow_id']}/approve",
        json={"approved": True, "plan_hash": workflow["plan_hash"]},
    )

    assert response.status_code == 200
    assert response.json()["workflow"]["status"] == "executing"
    assert response.json()["token_exchange"] == {
        "attempted": False,
        "reason": "workflow already executing",
    }


def test_approval_marks_workflow_failed_when_egress_skips_downstream_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryAgentServiceStore()
    egress = RecordingEgressClient(mcp_status="missing")
    monkeypatch.setattr(agent_app.httpx, "AsyncClient", egress.client_factory)
    monkeypatch.setattr(agent_app, "_exchange_obo_token", _fake_obo_exchange)
    app = create_app(
        store=store,
        intent_provider=FakeIntentProvider([_intent("restart_vm", {"vm_id": "vm-sample"})]),
    )
    client = _client(app, allowed_tools=["restart_vm"])
    client.post(
        "/token-context",
        json={"auth_context_ref": "raw-auth-token", "token_ref": "auth0:sample"},
    )
    workflow = client.post(
        "/workflows/plan",
        json={"query": "Restart vm-sample", "session_id": "session-1", "user_id": "user-1"},
    ).json()["workflow"]

    response = client.post(
        f"/workflows/{workflow['workflow_id']}/approve",
        json={"approved": True, "plan_hash": workflow["plan_hash"]},
    )

    assert response.status_code == 502
    restored = client.get(f"/workflows/{workflow['workflow_id']}").json()["workflow"]
    assert restored["status"] == "failed"


def test_approval_expiry_is_checked_before_egress_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExpiringDateTime(datetime):
        calls = 0

        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            _ = tz
            cls.calls += 1
            base = datetime(2026, 1, 1, tzinfo=UTC)
            return base if cls.calls == 1 else base + timedelta(minutes=20)

    store = InMemoryAgentServiceStore()
    egress = RecordingEgressClient()
    monkeypatch.setattr(agent_app, "datetime", ExpiringDateTime)
    monkeypatch.setattr(agent_app.httpx, "AsyncClient", egress.client_factory)
    monkeypatch.setattr(agent_app, "_exchange_obo_token", _fake_obo_exchange)
    app = create_app(
        store=store,
        intent_provider=FakeIntentProvider([_intent("restart_vm", {"vm_id": "vm-sample"})]),
    )
    client = _client(app, allowed_tools=["restart_vm"])
    client.post(
        "/token-context",
        json={"auth_context_ref": "raw-auth-token", "token_ref": "auth0:sample"},
    )
    workflow = client.post(
        "/workflows/plan",
        json={"query": "Restart vm-sample", "session_id": "session-1", "user_id": "user-1"},
    ).json()["workflow"]

    response = client.post(
        f"/workflows/{workflow['workflow_id']}/approve",
        json={"approved": True, "plan_hash": workflow["plan_hash"]},
    )

    assert response.status_code == 502
    assert not egress.requests
    restored = client.get(f"/workflows/{workflow['workflow_id']}").json()["workflow"]
    assert restored["status"] == "failed"
    assert restored["egress_results"][0]["message"] == "approval_expired"


def test_advisory_provider_output_is_filtered_by_allowed_tools() -> None:
    provider = FakeIntentProvider(
        [
            ToolIntent(
                agent_name="llm",
                mcp_server="cloud-mcp",
                tool_name="update_iam_binding",
                arguments={"principal_id": "user-sample", "role": "roles/owner"},
                reason="Escalate privileges.",
                metadata_ref="anthropic:update_iam_binding",
            )
        ]
    )
    client = _client(create_app(intent_provider=provider), allowed_tools=[])

    response = client.post(
        "/workflows/plan",
        json={
            "query": "Please review IAM",
            "user_id": "user-1",
            "session_id": "session-1",
            "allowed_tools": [],
        },
    )

    assert response.status_code == 200
    workflow = response.json()["workflow"]
    assert workflow["tool_intents"] == []
    assert workflow["proposal"]["steps"] == []
    assert workflow["status"] == "ready"


def test_advisory_provider_output_can_add_valid_allowed_intent() -> None:
    provider = FakeIntentProvider(
        [
            ToolIntent(
                agent_name="llm",
                mcp_server="wrong-mcp",
                tool_name="inspect_vm",
                arguments={"vm_id": "vm-123"},
                reason="Inspect VM posture.",
                metadata_ref="anthropic:inspect_vm",
            )
        ]
    )
    client = _client(create_app(intent_provider=provider), allowed_tools=["inspect_vm"])

    response = client.post(
        "/workflows/plan",
        json={
            "query": "Can you inspect runtime posture?",
            "user_id": "user-1",
            "session_id": "session-1",
            "allowed_tools": ["inspect_vm"],
        },
    )

    assert response.status_code == 200
    workflow = response.json()["workflow"]
    assert [intent["tool_name"] for intent in workflow["tool_intents"]] == ["inspect_vm"]
    assert workflow["tool_intents"][0]["mcp_server"] == "cloud-mcp"


def test_dispatcher_accepts_valid_allowed_intent() -> None:
    dispatcher = ToolIntentDispatcher()

    result = dispatcher.dispatch(
        PlanWorkflowRequest(
            query="Inspect VM",
            user_id="user-1",
            session_id="session-1",
            allowed_tools=["inspect_vm"],
        ),
        [
            ToolIntent(
                agent_name="google_adk_coordinator",
                mcp_server="wrong-mcp",
                tool_name="inspect_vm",
                arguments={"vm_id": "vm-1"},
                reason="Inspect VM posture.",
                metadata_ref="google_adk:inspect_vm",
            )
        ],
    )

    assert [intent.tool_name for intent in result.tool_intents] == ["inspect_vm"]
    assert result.steps[0].downstream_audience == "cloud-mcp"
    assert result.policy.requires_hitl is False


def test_dispatcher_rejects_invalid_or_disallowed_intents() -> None:
    dispatcher = ToolIntentDispatcher()

    result = dispatcher.dispatch(
        PlanWorkflowRequest(
            query="Escalate IAM",
            user_id="user-1",
            session_id="session-1",
            allowed_tools=["inspect_vm"],
        ),
        [
            ToolIntent(
                agent_name="google_adk_coordinator",
                mcp_server="cloud-mcp",
                tool_name="update_iam_binding",
                arguments={"principal_id": "user-sample", "role": "roles/owner"},
                reason="Escalate privileges.",
                metadata_ref="google_adk:update_iam_binding",
            ),
            ToolIntent(
                agent_name="google_adk_coordinator",
                mcp_server="cloud-mcp",
                tool_name="missing_tool",
                arguments={},
                reason="Unknown tool.",
                metadata_ref="google_adk:missing_tool",
            ),
        ],
    )

    assert result.tool_intents == []
    assert result.steps == []
    assert result.policy.requires_hitl is False


def test_dispatcher_marks_mutating_intent_as_hitl_gated() -> None:
    dispatcher = ToolIntentDispatcher()

    result = dispatcher.dispatch(
        PlanWorkflowRequest(
            query="Restart VM",
            user_id="user-1",
            session_id="session-1",
            allowed_tools=["restart_vm"],
            token_scopes=["write:vm"],
        ),
        [
            ToolIntent(
                agent_name="google_adk_coordinator",
                mcp_server="cloud-mcp",
                tool_name="restart_vm",
                arguments={"vm_id": "vm-1"},
                reason="Restart requested.",
                metadata_ref="google_adk:restart_vm",
            )
        ],
    )

    assert result.policy.requires_hitl is True
    assert result.policy.blast_radius == "medium"
    assert result.steps[0].operation_type == "WRITE"


async def test_google_adk_provider_fails_when_optional_runtime_is_missing(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr("agent_service.providers._load_adk_types", lambda: None)
    provider = GoogleAdkToolIntentProvider(enabled=True)

    with pytest.raises(RuntimeError, match="Google ADK agent runtime is unavailable"):
        await provider.propose(
            SanitizedWorkflowContext(
                query="Inspect VM",
                user_id="user-1",
                session_id="session-1",
                allowed_tools=["inspect_vm"],
            ),
            allowed_tool_names={"inspect_vm"},
            available_tool_names={"inspect_vm"},
        )


async def test_google_adk_provider_fails_when_runtime_returns_no_output(
    monkeypatch: Any,
) -> None:
    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            _ = kwargs

    class FakePart:
        @classmethod
        def from_text(cls, *, text: str) -> FakePart:
            _ = text
            return cls()

    class FakeContent:
        def __init__(self, *, role: str, parts: list[FakePart]) -> None:
            _ = role, parts

    class FakeSessionService:
        async def create_session(self, **kwargs: Any) -> object:
            _ = kwargs
            return object()

    class FakeRunner:
        def __init__(self, **kwargs: Any) -> None:
            _ = kwargs

        async def run_async(self, **kwargs: Any) -> Any:
            _ = kwargs
            if False:
                yield object()

    monkeypatch.setattr(
        "agent_service.providers._load_adk_types",
        lambda: AdkRuntimeTypes(
            agent_type=FakeAgent,
            content_type=FakeContent,
            part_type=FakePart,
            runner_type=FakeRunner,
            session_service_type=FakeSessionService,
        ),
    )
    provider = GoogleAdkToolIntentProvider(enabled=True)

    with pytest.raises(RuntimeError, match="Google ADK agent runtime returned no output"):
        await provider.run(
            SanitizedWorkflowContext(
                query="Inspect VM",
                user_id="user-1",
                session_id="session-1",
                allowed_tools=["inspect_vm"],
            ),
            allowed_tool_names={"inspect_vm"},
            available_tool_names={"inspect_vm"},
        )


async def test_google_adk_provider_retries_transient_runtime_failure(
    monkeypatch: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    attempts = 0
    secret = "test-anthropic-secret"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    caplog.set_level(logging.WARNING, logger="agent_service.providers")

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            _ = kwargs

    class FakePart:
        def __init__(self, text: str = "") -> None:
            self.text = text

        @classmethod
        def from_text(cls, *, text: str) -> FakePart:
            return cls(text)

    class FakeContent:
        def __init__(self, *, role: str, parts: list[FakePart]) -> None:
            self.role = role
            self.parts = parts

    class FakeEvent:
        def __init__(self, text: str) -> None:
            self.content = FakeContent(role="model", parts=[FakePart(text)])

        def is_final_response(self) -> bool:
            return True

    class FakeSessionService:
        async def create_session(self, **kwargs: Any) -> object:
            _ = kwargs
            return object()

    class FakeRunner:
        def __init__(self, **kwargs: Any) -> None:
            _ = kwargs

        async def run_async(self, **kwargs: Any) -> Any:
            nonlocal attempts
            _ = kwargs
            attempts += 1
            if attempts == 1:
                raise RuntimeError(f"temporary provider failure {secret}")
            yield FakeEvent('{"assistant_message":"Recovered.","tool_intents":[]}')

    monkeypatch.setattr(
        "agent_service.providers._load_adk_types",
        lambda: AdkRuntimeTypes(
            agent_type=FakeAgent,
            content_type=FakeContent,
            part_type=FakePart,
            runner_type=FakeRunner,
            session_service_type=FakeSessionService,
        ),
    )
    provider = GoogleAdkToolIntentProvider(enabled=True)

    result = await provider.run(
        SanitizedWorkflowContext(
            query="Inspect VM",
            user_id="user-1",
            session_id="session-1",
            allowed_tools=["inspect_vm"],
        ),
        allowed_tool_names={"inspect_vm"},
        available_tool_names={"inspect_vm"},
    )

    assert attempts == 2
    assert result.assistant_message == "Recovered."
    assert secret not in caplog.text
    assert "[redacted]" in caplog.text


async def test_google_adk_provider_builds_adk_agent_when_runtime_is_available(
    monkeypatch: Any,
) -> None:
    constructed: dict[str, Any] = {}

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            constructed["agent"] = kwargs

    class FakeAnthropicLlm:
        def __init__(self, *, model: str) -> None:
            self.model = model

    class FakePart:
        def __init__(self, text: str) -> None:
            self.text = text

        @classmethod
        def from_text(cls, *, text: str) -> FakePart:
            constructed["prompt"] = text
            return cls(text)

    class FakeContent:
        def __init__(self, *, role: str, parts: list[FakePart]) -> None:
            self.role = role
            self.parts = parts

    class FakeEvent:
        def __init__(self, text: str) -> None:
            self.content = FakeContent(role="model", parts=[FakePart(text)])

        def is_final_response(self) -> bool:
            return True

    class FakeSessionService:
        async def create_session(self, **kwargs: Any) -> object:
            constructed["session"] = kwargs
            return object()

    class FakeRunner:
        def __init__(self, **kwargs: Any) -> None:
            constructed["runner"] = kwargs

        async def run_async(self, **kwargs: Any) -> Any:
            constructed["run"] = kwargs
            yield FakeEvent(
                '{"assistant_message":"I will prepare the VM restart workflow.",'
                '"tool_intents":[{"tool_name":"restart_vm",'
                '"arguments":{"vm_id":"vm-1"},"reason":"ADK selected restart."}]}'
            )

    monkeypatch.setattr(
        "agent_service.providers._load_adk_types",
        lambda: AdkRuntimeTypes(
            agent_type=FakeAgent,
            content_type=FakeContent,
            part_type=FakePart,
            runner_type=FakeRunner,
            session_service_type=FakeSessionService,
            anthropic_llm_type=FakeAnthropicLlm,
        ),
    )
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("GOOGLE_ADK_MODEL", raising=False)
    provider = GoogleAdkToolIntentProvider(enabled=True)

    result = await provider.run(
        SanitizedWorkflowContext(
            query="Restart vm-sample",
            user_id="user-1",
            session_id="session-1",
            allowed_tools=["restart_vm"],
        ),
        allowed_tool_names={"restart_vm"},
        available_tool_names={"restart_vm"},
    )

    assert constructed["agent"]["name"] == "magnum_opus_coordinator"
    assert isinstance(constructed["agent"]["model"], FakeAnthropicLlm)
    assert constructed["agent"]["model"].model == "claude-haiku-4-5-20251001"
    assert constructed["agent"]["tools"] == []
    assert constructed["runner"]["agent"] is not None
    assert constructed["run"]["user_id"] == "user-1"
    assert "raw" not in constructed["prompt"]
    assert result.assistant_message == "I will prepare the VM restart workflow."
    assert [intent.tool_name for intent in result.tool_intents] == ["restart_vm"]
    assert result.tool_intents[0].agent_name == "google_adk_coordinator"
    assert result.tool_intents[0].arguments == {"vm_id": "vm-1"}


def test_thread_create_and_restore_return_sanitized_ag_ui_state() -> None:
    client = _client(create_app())

    create_response = client.post(
        "/threads",
        json={
            "threadId": "thread-1",
            "user_id": "user-1",
            "session_id": "session-1",
            "messages": [{"role": "user", "content": "Check DNS"}],
            "state": {
                "auth_context_ref": "raw-auth-token",
                "authContextRef": "raw-auth-token-camel",
                "token_ref": "token-1",
                "nested": {"Authorization": "Bearer raw", "safe": True},
            },
        },
    )

    assert create_response.status_code == 200
    thread = create_response.json()["thread"]
    assert thread["threadId"] == "thread-1"
    assert thread["messages"] == [{"role": "user", "content": "Check DNS"}]
    assert "auth_context_ref" not in thread["state"]
    assert "authContextRef" not in thread["state"]
    assert thread["state"]["nested"] == {"safe": True}
    assert thread["state"]["token_ref"] == "auth0:sample"

    restore_response = client.get(
        "/threads/thread-1",
        params={"user_id": "user-1", "session_id": "session-1"},
    )

    assert restore_response.status_code == 200
    assert restore_response.json()["thread"] == thread


def test_thread_snapshot_is_persisted_when_workflow_plan_includes_thread_id() -> None:
    client = _client_with_intents(
        [_intent("inspect_dns_record", {"record_name": "app.example.com"})]
    )

    response = client.post(
        "/workflows/plan",
        json={
            "query": "Check DNS health for app.example.com",
            "user_id": "user-1",
            "session_id": "session-1",
            "threadId": "thread-1",
            "messages": [{"role": "user", "content": "Check DNS health"}],
            "state": {"authContextRef": "raw-auth-token", "tokenRef": "token-1"},
        },
    )

    assert response.status_code == 200
    restore_response = client.get(
        "/threads/thread-1",
        params={"user_id": "user-1", "session_id": "session-1"},
    )

    thread = restore_response.json()["thread"]
    assert "authContextRef" not in thread["state"]
    assert thread["state"]["token_ref"] == "auth0:sample"
    assert thread["state"]["workflow"]["workflow_id"] == response.json()["workflow"]["workflow_id"]


def test_redis_store_fails_closed_when_redis_write_fails() -> None:
    class FailingRedis:
        async def get(self, key: str) -> bytes | str | None:
            raise OSError("redis down")

        async def set(self, key: str, value: str, *, ex: int | None = None) -> object:
            raise OSError("redis down")

    store = RedisAgentServiceStore(FailingRedis())
    client = _client(
        create_app(
            store=store,
            intent_provider=FakeIntentProvider(
                [_intent("inspect_dns_record", {"record_name": "app.example.com"})]
            ),
        )
    )

    with pytest.raises(OSError, match="redis down"):
        client.post(
            "/workflows/plan",
            json={
                "query": "Check DNS health for app.example.com",
                "user_id": "user-1",
                "session_id": "session-1",
            },
        )


async def test_redis_store_round_trips_auth_context_record() -> None:
    class RecordingRedis:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        async def get(self, key: str) -> bytes | str | None:
            return self.values.get(key)

        async def set(self, key: str, value: str, *, ex: int | None = None) -> object:
            self.values[key] = value
            return "OK"

    store = RedisAgentServiceStore(RecordingRedis())
    await store.register_auth_context(
        TokenRegistryRecord(
            user_id="user-1",
            session_id="session-1",
            token_ref="auth0:sample",
            auth_context_ref="raw-auth-token",
        )
    )

    assert (
        await store.get_auth_context(
            user_id="user-1",
            session_id="session-1",
            token_ref="auth0:sample",
        )
        == "raw-auth-token"
    )


class RecordingEgressClient:
    def __init__(self, *, mcp_status: str = "completed") -> None:
        self.mcp_status = mcp_status
        self.requests: list[dict[str, Any]] = []

    def client_factory(self, *args: Any, **kwargs: Any) -> RecordingEgressClient:
        _ = args, kwargs
        return self

    async def __aenter__(self) -> RecordingEgressClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        _ = exc_type, exc_value, traceback

    async def post(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any],
    ) -> EgressResponse:
        assert path == "/egress/mcp"
        assert headers is not None
        assert "x-magnum-session-context" in headers
        assert "x-magnum-session-signature" in headers
        self.requests.append(json)
        return EgressResponse(json, mcp_status=self.mcp_status)


class EgressResponse:
    def __init__(self, request: dict[str, Any], *, mcp_status: str) -> None:
        self._request = request
        self._mcp_status = mcp_status

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        outbound: dict[str, object] = {}
        if self._mcp_status != "missing":
            outbound["mcp_result"] = {
                "is_error": self._mcp_status == "failed",
                "status": self._mcp_status,
            }
        return {
            "approval_id": self._request["approval_id"],
            "arguments": self._request["arguments"],
            "method": self._request["method"],
            "obo_token_ref": self._request["obo_token_ref"],
            "outbound": outbound,
            "primitive": self._request["primitive"],
            "target_mcp": self._request["target_mcp"],
            "tool_name": self._request["tool_name"],
            "workflow_id": self._request["workflow_id"],
        }


async def _fake_obo_exchange(
    record: Any,
    approval: Any,
    auth_context_ref: str,
) -> WorkflowTokenExchangeResponse:
    assert auth_context_ref == "raw-auth-token"
    return WorkflowTokenExchangeResponse(
        access_token="obo-access-token",
        audience="https://api.example.test",
        expires_at=approval.expires_at,
        scopes=sorted(set(record.policy.required_scopes).union({"write:vm"})),
    )


async def _fake_obo_exchange_without_audience(
    record: Any,
    approval: Any,
    auth_context_ref: str,
) -> WorkflowTokenExchangeResponse:
    assert auth_context_ref == "raw-auth-token"
    return WorkflowTokenExchangeResponse(
        access_token="obo-access-token",
        audience=None,
        expires_at=approval.expires_at,
        scopes=sorted(set(record.policy.required_scopes).union({"write:vm"})),
    )


def _parse_sse_data_events(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        assert lines
        assert all(line.startswith("data: ") for line in lines)
        decoded: object = json.loads(
            "\n".join(line.removeprefix("data: ") for line in lines)
        )
        assert isinstance(decoded, dict)
        events.append(decoded)
    return events

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

import httpx
from agent_service_supervisor import routes
from agent_service_supervisor.app import create_app
from agent_service_supervisor.config import SupervisorSettings
from agent_service_supervisor.discovery_sqlite import SubagentRecord
from agent_service_supervisor.workflow_orchestrator import WorkflowOrchestrator
from fastapi.testclient import TestClient


def test_auth0_session_route_materializes_management_metadata(monkeypatch, tmp_path) -> None:
    emitted_events: list[dict[str, Any]] = []

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.posts: list[tuple[str, dict[str, str]]] = []

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            return None

        async def post(
            self,
            url: str,
            data: dict[str, str],
        ) -> httpx.Response:
            self.posts.append((url, data))
            assert url == "https://samples.auth0.com/oauth/token"
            assert data == {
                "grant_type": "client_credentials",
                "client_id": "management-client-id",
                "client_secret": "management-secret",
                "audience": "https://samples.auth0.com/api/v2/",
                "scope": "read:users read:users_app_metadata",
            }
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={"access_token": "management-token", "token_type": "Bearer"},
            )

        async def get(
            self,
            url: str,
            headers: dict[str, str],
        ) -> httpx.Response:
            assert url.endswith("/api/v2/users/auth0%7Cuser-1")
            assert headers["authorization"] == "Bearer management-token"
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json={
                    "app_metadata": {
                        "magnum_opus": {
                            "allowed_scopes": ["read:identity", "read:apps"],
                            "allowed_mcp_tools": [
                                "get_identity_profile",
                                "get_developer_app",
                            ],
                            "persona_traits": ["identity-aware", "developer-focused"],
                        }
                    }
                },
            )

    monkeypatch.setattr(routes.httpx, "AsyncClient", FakeAsyncClient)

    async def capture_event(**kwargs: Any) -> None:
        emitted_events.append(kwargs)

    monkeypatch.setattr(routes, "_emit_sidecar_event", capture_event)
    app = create_app(
        SupervisorSettings(
            subagent_db_path=tmp_path / "subagents.sqlite",
            auth0_domain="samples.auth0.com",
            auth0_audience="https://api.example.test",
            auth0_management_client_id="management-client-id",
            auth0_management_client_secret="management-secret",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/identity/auth0/session",
            json={
                "user_id": "auth0|user-1",
                "user_email": "sample@example.com",
                "user_name": "sample",
                "session_id": "auth0-session-1",
                "token_ref": "auth0:sample",
                "token_scopes": ["openid", "profile"],
                "audience": "https://api.example.test",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_ref"].startswith("auth0:")
    assert payload["scope"] == "read:apps read:identity"
    assert payload["user_id"] == "auth0|user-1"
    assert payload["user_email"] == "sample@example.com"
    assert payload["allowed_tools"] == ["get_developer_app", "get_identity_profile"]
    assert payload["persona"]["display_name"] == "sample"
    assert payload["persona"]["traits"] == ["developer-focused", "identity-aware"]
    assert any(event["event_type"] == "on_login" for event in emitted_events)
    assert "management-secret" not in str(payload)


def test_plan_approve_execute_workflow_in_manifest_order(tmp_path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        payloads: dict[str, dict[str, Any]] = {
            "planner-agent": {
                "proposals": [
                    {
                        "agent_name": "planner",
                        "tool_name": "propose_workflow_plan",
                        "arguments": {"query": "Check user sample-user and app sample-app"},
                        "reason": "planner",
                    }
                ]
            },
            "identity-agent": {
                "proposals": [
                    {
                        "agent_name": "identity",
                        "tool_name": "get_identity_profile",
                        "arguments": {"subject_user_id": "sample-user"},
                        "reason": "identity",
                    }
                ]
            },
            "developer-agent": {
                "proposals": [
                    {
                        "agent_name": "developer",
                        "tool_name": "get_developer_app",
                        "arguments": {"appid": "sample-app"},
                        "reason": "developer",
                    }
                ]
            },
        }
        return httpx.Response(200, json=payloads[host])

    app = create_app(SupervisorSettings(subagent_db_path=tmp_path / "subagents.sqlite"))
    _seed_legacy_subagents(app)
    app.state.workflow_orchestrator = WorkflowOrchestrator(
        app.state.subagent_discovery,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with TestClient(app) as client:
        planned = client.post(
            "/workflows/plan",
            json={
                "question": "Check user sample-user and app sample-app",
                "user_id": "sample-user",
                "session_id": "session-1",
                "token_ref": "auth0:sample",
                "token_scopes": ["read:workflow", "read:users", "read:apps"],
                "allowed_tools": ["get_identity_profile", "get_developer_app"],
            },
        )
        assert planned.status_code == 200
        manifest = planned.json()

        assert manifest["status"]["status"] == "awaiting_approval"
        assert [step["action"] for step in manifest["plan"]["steps"]] == [
            "propose_workflow_plan",
            "get_identity_profile",
            "get_developer_app",
        ]
        scopes_by_action = {
            step["action"]: step["required_scopes"] for step in manifest["plan"]["steps"]
        }
        assert scopes_by_action["get_identity_profile"] == ["read:user:sample-user"]
        assert scopes_by_action["get_developer_app"] == ["read:client:sample-app"]
        assert manifest["authorization"]["scopes"] == [
            "read:client:sample-app",
            "read:user:sample-user",
            "read:workflow",
        ]
        assert manifest["events"][0]["attributes"]["filtered_proposal_count"] == 0

        approved = client.post(
            f"/workflows/{manifest['workflow_id']}/approve",
            json={
                "approved": True,
                "approved_by_user_id": "sample-user",
                "plan_hash": manifest["plan_hash"],
                "token_ref": "auth0:sample",
            },
        )
        assert approved.status_code == 200
        result = approved.json()

    assert result["status"]["status"] == "approved"
    assert result["step_results"] == []
    assert [event["event_type"] for event in result["events"]] == [
        "workflow.planned",
        "workflow.awaiting_approval",
        "workflow.approved",
        "workflow.execution_delegated",
    ]


def test_plan_workflow_filters_proposals_to_allowed_tools(tmp_path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        payloads: dict[str, dict[str, Any]] = {
            "planner-agent": {
                "proposals": [
                    {
                        "agent_name": "planner",
                        "tool_name": "propose_workflow_plan",
                        "arguments": {"query": "Check user sample-user and app sample-app"},
                    }
                ]
            },
            "identity-agent": {
                "proposals": [
                    {
                        "agent_name": "identity",
                        "tool_name": "get_identity_profile",
                        "arguments": {"subject_user_id": "sample-user"},
                    }
                ]
            },
            "developer-agent": {
                "proposals": [
                    {
                        "agent_name": "developer",
                        "tool_name": "get_developer_app",
                        "arguments": {"appid": "sample-app"},
                    }
                ]
            },
        }
        return httpx.Response(200, json=payloads[host])

    app = create_app(SupervisorSettings(subagent_db_path=tmp_path / "subagents.sqlite"))
    _seed_legacy_subagents(app)
    app.state.workflow_orchestrator = WorkflowOrchestrator(
        app.state.subagent_discovery,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with TestClient(app) as client:
        planned = client.post(
            "/workflows/plan",
            json={
                "question": "Check user sample-user and app sample-app",
                "user_id": "sample-user",
                "session_id": "session-1",
                "token_ref": "auth0:sample",
                "token_scopes": ["read:workflow", "read:users", "read:apps"],
                "allowed_tools": ["get_identity_profile"],
            },
        )

    assert planned.status_code == 200
    manifest = planned.json()
    assert [step["action"] for step in manifest["plan"]["steps"]] == [
        "propose_workflow_plan",
        "get_identity_profile",
    ]
    assert manifest["events"][0]["attributes"]["filtered_proposal_count"] == 1


def test_plan_workflow_empty_allowed_tools_keeps_only_orchestration(tmp_path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        payloads: dict[str, dict[str, Any]] = {
            "planner-agent": {
                "proposals": [
                    {
                        "agent_name": "planner",
                        "tool_name": "propose_workflow_plan",
                        "arguments": {"query": "Check user sample-user and app sample-app"},
                    }
                ]
            },
            "identity-agent": {
                "proposals": [
                    {
                        "agent_name": "identity",
                        "tool_name": "get_identity_profile",
                        "arguments": {"subject_user_id": "sample-user"},
                    }
                ]
            },
            "developer-agent": {
                "proposals": [
                    {
                        "agent_name": "developer",
                        "tool_name": "get_developer_app",
                        "arguments": {"appid": "sample-app"},
                    }
                ]
            },
        }
        return httpx.Response(200, json=payloads[host])

    app = create_app(SupervisorSettings(subagent_db_path=tmp_path / "subagents.sqlite"))
    _seed_legacy_subagents(app)
    app.state.workflow_orchestrator = WorkflowOrchestrator(
        app.state.subagent_discovery,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with TestClient(app) as client:
        planned = client.post(
            "/workflows/plan",
            json={
                "question": "Check user sample-user and app sample-app",
                "user_id": "sample-user",
                "session_id": "session-1",
                "token_ref": "auth0:sample",
                "token_scopes": ["read:workflow", "read:users", "read:apps"],
                "allowed_tools": [],
            },
        )

    assert planned.status_code == 200
    manifest = planned.json()
    assert [step["action"] for step in manifest["plan"]["steps"]] == [
        "propose_workflow_plan"
    ]
    assert manifest["events"][0]["attributes"]["filtered_proposal_count"] == 2


def test_plan_workflow_rejects_unmaterializable_dynamic_scope(tmp_path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        payloads: dict[str, dict[str, Any]] = {
            "planner-agent": {
                "proposals": [
                    {
                        "agent_name": "planner",
                        "tool_name": "propose_workflow_plan",
                        "arguments": {"query": "Check an app without an app id"},
                    }
                ]
            },
            "identity-agent": {"proposals": []},
            "developer-agent": {
                "proposals": [
                    {
                        "agent_name": "developer",
                        "tool_name": "get_developer_app",
                        "arguments": {},
                    }
                ]
            },
        }
        return httpx.Response(200, json=payloads[host])

    app = create_app(SupervisorSettings(subagent_db_path=tmp_path / "subagents.sqlite"))
    _seed_legacy_subagents(app)
    app.state.workflow_orchestrator = WorkflowOrchestrator(
        app.state.subagent_discovery,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with TestClient(app) as client:
        planned = client.post(
            "/workflows/plan",
            json={
                "question": "Check an app without an app id",
                "user_id": "sample-user",
                "session_id": "session-1",
                "token_ref": "auth0:sample",
                "token_scopes": ["read:workflow", "read:apps"],
            },
        )

    assert planned.status_code == 422
    detail = planned.json()["detail"]
    assert "could not materialize workflow scopes for get_developer_app" in detail
    assert "appid" in detail


def _seed_legacy_subagents(app: Any) -> None:
    now = datetime.now(UTC)
    records = [
        SubagentRecord(
            agent_name="planner",
            base_url="http://planner-agent:8080",
            mcp_server_name="planner-mcp",
            enabled=True,
            priority=10,
            updated_at=now,
        ),
        SubagentRecord(
            agent_name="identity",
            base_url="http://identity-agent:8080",
            mcp_server_name="identity-mcp",
            enabled=True,
            priority=20,
            updated_at=now,
        ),
        SubagentRecord(
            agent_name="developer",
            base_url="http://developer-agent:8080",
            mcp_server_name="developer-mcp",
            enabled=True,
            priority=30,
            updated_at=now,
        ),
    ]

    async def seed() -> None:
        for record in records:
            await app.state.subagent_discovery.upsert_subagent(record)

    asyncio.run(seed())

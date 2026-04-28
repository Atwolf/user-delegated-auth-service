from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx
from agent_service_supervisor import routes
from agent_service_supervisor.app import create_app
from agent_service_supervisor.config import SupervisorSettings
from agent_service_supervisor.workflow_orchestrator import WorkflowOrchestrator
from fastapi.testclient import TestClient
from token_broker import Auth0ClientCredentialsConfig, Auth0ClientCredentialsTokenResponse


def test_client_credentials_route_uses_secret_without_persisting_it(monkeypatch, tmp_path) -> None:
    class FakeAuth0ClientCredentialsClient:
        async def __aenter__(self) -> FakeAuth0ClientCredentialsClient:
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            return None

        async def exchange(
            self,
            config: Auth0ClientCredentialsConfig,
        ) -> Auth0ClientCredentialsTokenResponse:
            assert config.client_secret.get_secret_value() == "client-secret"
            return Auth0ClientCredentialsTokenResponse.from_access_token(
                access_token="issued-access-token",
                token_type="Bearer",
                expires_in=3600,
                scopes=config.scopes,
                audience=config.audience,
            )

    monkeypatch.setattr(
        routes,
        "Auth0ClientCredentialsClient",
        FakeAuth0ClientCredentialsClient,
    )
    app = create_app(SupervisorSettings(subagent_db_path=tmp_path / "subagents.sqlite"))

    with TestClient(app) as client:
        response = client.post(
            "/identity/client-credentials/token",
            json={
                "domain": "samples.auth0.com",
                "token_endpoint": "https://samples.auth0.com/oauth/token",
                "jwks_endpoint": "https://samples.auth0.com/.well-known/jwks.json",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "scope": "openid profile email",
                "audience": "https://api.example.test",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"] == "issued-access-token"
    assert payload["scope"] == "openid profile email"
    assert payload["token_ref"].startswith("auth0:")
    assert "client-secret" not in str(payload)


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
        assert manifest["authorization"]["scopes"] == [
            "DOE.Developer.sample-app",
            "DOE.Identity.sample-user",
            "DOE.Workflow.plan",
        ]

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

    assert result["status"]["status"] == "completed"
    assert [step["action"] for step in result["step_results"]] == [
        "propose_workflow_plan",
        "get_identity_profile",
        "get_developer_app",
    ]
    assert [event["event_type"] for event in result["events"]] == [
        "workflow.planned",
        "workflow.awaiting_approval",
        "workflow.approved",
        "workflow.step_executed",
        "workflow.step_executed",
        "workflow.step_executed",
        "workflow.completed",
    ]

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from egress_gateway.app import create_app
from fastapi.testclient import TestClient
from session_state import TrustedSessionContext, signed_session_context_headers
from workflow_core import ExecutionGrant, sign_execution_grant

egress_app = importlib.import_module("egress_gateway.app")


@pytest.fixture(autouse=True)
def internal_auth_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_AUTH_SECRET", "test-internal-secret")


@pytest.fixture(autouse=True)
def mcp_client(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMcpResult:
        is_error = False
        data = {"status": "ok"}
        structured_content: dict[str, object] = {}
        content: list[object] = []

    class FakeMcpClient:
        def __init__(self, endpoint: str, auth: str) -> None:
            self.endpoint = endpoint
            self.auth = auth

        async def __aenter__(self) -> FakeMcpClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            _ = args

        async def call_tool(
            self,
            name: str,
            arguments: dict[str, Any],
            *,
            raise_on_error: bool,
        ) -> FakeMcpResult:
            _ = name, arguments, raise_on_error
            return FakeMcpResult()

    monkeypatch.setattr(egress_app, "Client", FakeMcpClient)


def _request_payload(
    *,
    primitive: str = "discovery",
    method: str = "GET",
    access_token: str | None = None,
    target_mcp: str = "network-mcp",
    tool_name: str = "inspect_dns_record",
    include_execution_grant: bool = False,
) -> dict[str, object]:
    arguments = {"scope": "profile"}
    payload: dict[str, object] = {
        "primitive": primitive,
        "method": method,
        "target_mcp": target_mcp,
        "tool_name": tool_name,
        "arguments": arguments,
        "workflow_id": "workflow-123",
        "approval_id": "approval-456",
        "obo_token_ref": "token-ref-789",
    }
    if access_token is not None:
        payload["access_token"] = access_token
    if include_execution_grant:
        grant = _execution_grant(
            primitive=primitive,
            method=method,
            target_mcp=target_mcp,
            tool_name=tool_name,
            arguments=arguments,
        )
        payload["execution_grant"] = grant.model_dump(mode="json")
        payload["execution_grant_signature"] = sign_execution_grant(
            grant,
            secret="test-internal-secret",
        )
        payload["token_audience"] = "https://api.example.test"
        payload["token_scopes"] = ["write:vm"]
    return payload


def _client(
    *,
    user_id: str = "user-1",
    session_id: str = "session-1",
    tenant_id: str | None = None,
) -> TestClient:
    return TestClient(
        create_app(),
        headers=_signed_context_headers(
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
) -> dict[str, str]:
    return signed_session_context_headers(
        TrustedSessionContext(
            allowed_tools=None,
            correlation_id="test-egress",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            session_id=session_id,
            tenant_id=tenant_id,
            token_ref="auth0:sample",
            token_scopes=["write:vm"],
            user_id=user_id,
        ),
        secret="test-internal-secret",
    )


def _execution_grant(
    *,
    primitive: str,
    method: str,
    target_mcp: str,
    tool_name: str,
    arguments: dict[str, object],
    audience: str | None = "https://api.example.test",
    expires_at: datetime | None = None,
    required_scopes: list[str] | None = None,
) -> ExecutionGrant:
    return ExecutionGrant(
        approval_id="approval-456",
        arguments=arguments,
        audience=audience,
        approved_by_user_id="user-1",
        correlation_id="workflow-123:step-1",
        expires_at=expires_at or datetime.now(UTC) + timedelta(minutes=5),
        method=method,
        plan_hash="sha256:test",
        primitive=primitive,
        required_scopes=required_scopes or ["write:vm"],
        session_id="session-1",
        step_id="step-1",
        target_mcp=target_mcp,
        tenant_id=None,
        tool_name=tool_name,
        user_id="user-1",
        workflow_id="workflow-123",
    )


def _attach_grant(payload: dict[str, object], grant: ExecutionGrant) -> dict[str, object]:
    payload["execution_grant"] = grant.model_dump(mode="json")
    payload["execution_grant_signature"] = sign_execution_grant(
        grant,
        secret="test-internal-secret",
    )
    payload["token_audience"] = grant.audience
    payload["token_scopes"] = list(grant.required_scopes)
    return payload


def test_healthz() -> None:
    client = _client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_discovery_requires_grant_and_redacts_auth_headers() -> None:
    client = _client()

    response = client.post(
        "/egress/mcp",
        json=_request_payload(access_token="secret-token", include_execution_grant=True),
    )

    assert response.status_code == 200
    headers = response.json()["outbound"]["headers"]
    assert headers == {"Authorization": "[REDACTED]", "X-AuthN-Context": "[REDACTED]"}
    assert "secret-token" not in str(response.json())


def test_get_discovery_denies_missing_execution_grant() -> None:
    client = _client()

    response = client.post(
        "/egress/mcp",
        json=_request_payload(access_token="secret-token"),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "execution_grant is required for outbound MCP execution"
    }


def test_mcp_requires_signed_internal_context() -> None:
    client = TestClient(create_app())

    response = client.post("/egress/mcp", json=_request_payload())

    assert response.status_code == 401
    assert response.json() == {"detail": "signed session context is required"}


def test_post_execution_requires_access_token() -> None:
    client = _client()

    response = client.post(
        "/egress/mcp",
        json=_request_payload(
            primitive="execute",
            method="POST",
            access_token="secret-token",
            target_mcp="cloud-mcp",
            tool_name="restart_vm",
            include_execution_grant=True,
        ),
    )

    assert response.status_code == 200
    assert response.json()["outbound"]["method"] == "POST"


def test_post_execution_redacts_authorization_in_response() -> None:
    client = _client()

    response = client.post(
        "/egress/mcp",
        json=_request_payload(
            primitive="execute",
            method="POST",
            access_token="secret-token",
            target_mcp="cloud-mcp",
            tool_name="restart_vm",
            include_execution_grant=True,
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["outbound"]["headers"]["Authorization"] == "[REDACTED]"
    assert "secret-token" not in str(body)


def test_post_execution_denies_missing_access_token() -> None:
    client = _client()

    response = client.post(
        "/egress/mcp",
        json=_request_payload(
            primitive="execute",
            method="POST",
            target_mcp="cloud-mcp",
            tool_name="restart_vm",
        ),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "access_token is required for outbound MCP execution"}


def test_mcp_transport_failure_is_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingMcpClient:
        def __init__(self, endpoint: str, auth: str) -> None:
            _ = endpoint, auth

        async def __aenter__(self) -> FailingMcpClient:
            raise OSError("mcp unavailable")

        async def __aexit__(self, *args: object) -> None:
            _ = args

    monkeypatch.setattr(egress_app, "Client", FailingMcpClient)
    client = _client()

    response = client.post(
        "/egress/mcp",
        json=_request_payload(
            primitive="execute",
            method="POST",
            access_token="secret-token",
            target_mcp="cloud-mcp",
            tool_name="restart_vm",
            include_execution_grant=True,
        ),
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "MCP transport call failed: OSError"}


def test_post_execution_denies_missing_execution_grant() -> None:
    client = _client()

    response = client.post(
        "/egress/mcp",
        json=_request_payload(
            primitive="execute",
            method="POST",
            access_token="secret-token",
            target_mcp="cloud-mcp",
            tool_name="restart_vm",
        ),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "execution_grant is required for outbound MCP execution"
    }


def test_post_execution_denies_invalid_grant_signature() -> None:
    client = _client()
    payload = _request_payload(
        primitive="execute",
        method="POST",
        access_token="secret-token",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
        include_execution_grant=True,
    )
    payload["execution_grant_signature"] = "invalid"

    response = client.post("/egress/mcp", json=payload)

    assert response.status_code == 403
    assert response.json() == {"detail": "invalid execution grant signature"}


@pytest.mark.parametrize(
    ("grant_update", "expected_detail"),
    [
        ({"workflow_id": "workflow-tampered"}, "workflow_id"),
        ({"approval_id": "approval-tampered"}, "approval_id"),
        ({"tool_name": "inspect_vm"}, "tool_name"),
        ({"target_mcp": "network-mcp"}, "target_mcp"),
    ],
)
def test_post_execution_denies_grant_field_mismatch(
    grant_update: dict[str, object],
    expected_detail: str,
) -> None:
    client = _client()
    payload = _request_payload(
        primitive="execute",
        method="POST",
        access_token="secret-token",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
    )
    grant = _execution_grant(
        primitive="execute",
        method="POST",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
        arguments={"scope": "profile"},
    ).model_copy(update=grant_update)
    _attach_grant(payload, grant)

    response = client.post("/egress/mcp", json=payload)

    assert response.status_code == 403
    assert response.json() == {
        "detail": f"execution grant does not match request: {expected_detail}"
    }


def test_post_execution_denies_modified_arguments() -> None:
    client = _client()
    payload = _request_payload(
        primitive="execute",
        method="POST",
        access_token="secret-token",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
        include_execution_grant=True,
    )
    payload["arguments"] = {"scope": "tampered"}

    response = client.post("/egress/mcp", json=payload)

    assert response.status_code == 403
    assert response.json() == {
        "detail": "execution grant does not match request: arguments"
    }


def test_post_execution_denies_cross_user_grant_replay() -> None:
    client = _client(user_id="user-2")
    payload = _request_payload(
        primitive="execute",
        method="POST",
        access_token="secret-token",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
        include_execution_grant=True,
    )

    response = client.post("/egress/mcp", json=payload)

    assert response.status_code == 403
    assert response.json() == {
        "detail": "execution grant does not match trusted session context: user_id"
    }


def test_post_execution_denies_cross_session_grant_replay() -> None:
    client = _client(session_id="session-2")
    payload = _request_payload(
        primitive="execute",
        method="POST",
        access_token="secret-token",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
        include_execution_grant=True,
    )

    response = client.post("/egress/mcp", json=payload)

    assert response.status_code == 403
    assert response.json() == {
        "detail": "execution grant does not match trusted session context: session_id"
    }


def test_post_execution_denies_cross_tenant_grant_replay() -> None:
    client = _client(tenant_id="tenant-b")
    payload = _request_payload(
        primitive="execute",
        method="POST",
        access_token="secret-token",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
    )
    grant = _execution_grant(
        primitive="execute",
        method="POST",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
        arguments={"scope": "profile"},
    ).model_copy(update={"tenant_id": "tenant-a"})
    _attach_grant(payload, grant)

    response = client.post("/egress/mcp", json=payload)

    assert response.status_code == 403
    assert response.json() == {
        "detail": "execution grant does not match trusted session context: tenant_id"
    }


def test_post_execution_denies_expired_grant() -> None:
    client = _client()
    payload = _request_payload(
        primitive="execute",
        method="POST",
        access_token="secret-token",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
    )
    grant = _execution_grant(
        primitive="execute",
        method="POST",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
        arguments={"scope": "profile"},
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    _attach_grant(payload, grant)

    response = client.post("/egress/mcp", json=payload)

    assert response.status_code == 403
    assert response.json() == {"detail": "execution grant has expired"}


def test_post_execution_denies_missing_scope() -> None:
    client = _client()
    payload = _request_payload(
        primitive="execute",
        method="POST",
        access_token="secret-token",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
        include_execution_grant=True,
    )
    payload["token_scopes"] = ["read:vm"]

    response = client.post("/egress/mcp", json=payload)

    assert response.status_code == 403
    assert response.json() == {"detail": "access token is missing grant-required scopes"}


def test_post_execution_denies_wrong_audience() -> None:
    client = _client()
    payload = _request_payload(
        primitive="execute",
        method="POST",
        access_token="secret-token",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
        include_execution_grant=True,
    )
    payload["token_audience"] = "https://wrong.example.test"

    response = client.post("/egress/mcp", json=payload)

    assert response.status_code == 403
    assert response.json() == {
        "detail": "access token audience does not match execution grant"
    }


def test_post_execution_denies_missing_grant_audience() -> None:
    client = _client()
    payload = _request_payload(
        primitive="execute",
        method="POST",
        access_token="secret-token",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
    )
    grant = _execution_grant(
        primitive="execute",
        method="POST",
        target_mcp="cloud-mcp",
        tool_name="restart_vm",
        arguments={"scope": "profile"},
        audience=None,
    )
    _attach_grant(payload, grant)

    response = client.post("/egress/mcp", json=payload)

    assert response.status_code == 403
    assert response.json() == {"detail": "execution grant audience is required"}


def test_post_execution_denies_unknown_tool_even_with_access_token() -> None:
    client = _client()

    response = client.post(
        "/egress/mcp",
        json=_request_payload(
            primitive="execute",
            method="POST",
            access_token="secret-token",
            tool_name="unknown_tool",
        ),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "known tool authorization is required for outbound MCP execution"
    }

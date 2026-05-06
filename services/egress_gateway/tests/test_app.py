from __future__ import annotations

from egress_gateway.app import create_app
from fastapi.testclient import TestClient


def _request_payload(
    *,
    primitive: str = "discovery",
    method: str = "GET",
    access_token: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "primitive": primitive,
        "method": method,
        "target_mcp": "identity-mcp",
        "tool_name": "list_tools",
        "arguments": {"scope": "profile"},
        "workflow_id": "workflow-123",
        "approval_id": "approval-456",
        "obo_token_ref": "token-ref-789",
    }
    if access_token is not None:
        payload["access_token"] = access_token
    return payload


def test_healthz() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_discovery_has_authn_context_without_authorization() -> None:
    client = TestClient(create_app())

    response = client.post("/egress/mcp", json=_request_payload())

    assert response.status_code == 200
    headers = response.json()["outbound"]["headers"]
    assert headers == {"X-AuthN-Context": "[REDACTED]"}
    assert "Authorization" not in headers


def test_post_execution_requires_access_token() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/egress/mcp",
        json=_request_payload(primitive="execute", method="POST", access_token="secret-token"),
    )

    assert response.status_code == 200
    assert response.json()["outbound"]["method"] == "POST"


def test_post_execution_redacts_authorization_in_response() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/egress/mcp",
        json=_request_payload(primitive="execute", method="POST", access_token="secret-token"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["outbound"]["headers"]["Authorization"] == "[REDACTED]"
    assert "secret-token" not in str(body)


def test_post_execution_denies_missing_access_token() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/egress/mcp",
        json=_request_payload(primitive="execute", method="POST"),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "access_token is required for outbound MCP execution"}

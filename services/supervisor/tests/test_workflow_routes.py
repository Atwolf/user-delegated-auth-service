from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any

import httpx
from agent_service_supervisor import routes
from agent_service_supervisor.app import create_app
from agent_service_supervisor.config import SupervisorSettings
from fastapi.testclient import TestClient
from observability_sidecar.models import AgenticTraceIngest, LogIngest
from observability_sidecar.store import InMemoryTelemetryStore
from session_state import TrustedSessionContext, signed_session_context_headers


def test_auth0_session_route_materializes_management_metadata(monkeypatch) -> None:
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
            auth0_domain="samples.auth0.com",
            auth0_audience="https://api.example.test",
            auth0_management_client_id="management-client-id",
            auth0_management_client_secret="management-secret",
            internal_service_auth_secret="test-internal-secret",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/identity/auth0/session",
            headers=_signed_context_headers(
                user_id="auth0|user-1",
                session_id="auth0-session-1",
                token_ref="auth0:sample",
                token_scopes=["openid", "profile"],
            ),
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


def test_auth0_session_route_requires_signed_internal_context() -> None:
    app = create_app(SupervisorSettings(internal_service_auth_secret="test-internal-secret"))

    with TestClient(app) as client:
        response = client.post(
            "/identity/auth0/session",
            json={
                "user_id": "auth0|user-1",
                "session_id": "auth0-session-1",
                "token_ref": "auth0:sample",
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "signed session context is required"}


def test_auth0_session_route_requires_magnum_opus_metadata(monkeypatch) -> None:
    response = _auth0_session_response(
        monkeypatch,
        user_payload={"app_metadata": {}},
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Auth0 user metadata is missing app_metadata.magnum_opus"
    }


def test_auth0_session_route_requires_explicit_allowed_scopes(monkeypatch) -> None:
    response = _auth0_session_response(
        monkeypatch,
        user_payload={
            "app_metadata": {
                "magnum_opus": {
                    "allowed_mcp_tools": ["get_identity_profile"],
                }
            }
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Auth0 user metadata field app_metadata.magnum_opus.allowed_scopes is required"
    }


def test_auth0_session_route_requires_explicit_allowed_tools(monkeypatch) -> None:
    response = _auth0_session_response(
        monkeypatch,
        user_payload={
            "app_metadata": {
                "magnum_opus": {
                    "allowed_scopes": ["read:identity"],
                    "allowed_mcp_tools": [],
                }
            }
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Auth0 user metadata field app_metadata.magnum_opus.allowed_mcp_tools is required"
    }


def test_auth0_session_route_rejects_context_mismatch() -> None:
    app = create_app(SupervisorSettings(internal_service_auth_secret="test-internal-secret"))

    with TestClient(app) as client:
        response = client.post(
            "/identity/auth0/session",
            headers=_signed_context_headers(user_id="auth0|other-user"),
            json={
                "user_id": "auth0|user-1",
                "session_id": "auth0-session-1",
                "token_ref": "auth0:sample",
            },
        )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Auth0 metadata request does not match trusted session context: user_id"
    }


def test_supervisor_no_longer_exposes_legacy_workflow_routes() -> None:
    app = create_app(SupervisorSettings())

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/subagents").status_code == 404
        assert client.post("/workflows/plan", json={}).status_code == 404


async def test_sidecar_event_emission_redacts_auth0_session_materialization(
    monkeypatch,
) -> None:
    store = InMemoryTelemetryStore()

    class LocalSidecarClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            _ = args, kwargs

        async def __aenter__(self) -> LocalSidecarClient:
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            _ = exc_type, exc_value, traceback

        async def emit_trace(self, *, source_component: str, event: object) -> None:
            await store.append_trace(
                AgenticTraceIngest(source_component=source_component, event=event)
            )

        async def emit_log(
            self,
            *,
            source_component: str,
            level: str,
            message: str,
            attributes: dict[str, object] | None = None,
            trace_id: str | None = None,
            agentic_span_id: str | None = None,
        ) -> None:
            await store.append_log(
                LogIngest(
                    agentic_span_id=agentic_span_id,
                    attributes=attributes or {},
                    level=level,
                    message=message,
                    source_component=source_component,
                    trace_id=trace_id,
                )
            )

    monkeypatch.setattr(routes, "ObservabilitySidecarClient", LocalSidecarClient)

    await routes._emit_sidecar_event(
        settings=SupervisorSettings(observability_sidecar_url="http://sidecar.test"),
        event_type="identity.auth0_user_session_materialized",
        user_id="auth0|user-1",
        session_id="session-1",
        attributes={
            "allowed_tools": ["restart_vm"],
            "authorization": "Bearer raw-access-token",
            "token_ref": "auth0:token-ref-secret",
        },
    )

    serialized = "\n".join(
        [trace.model_dump_json() for trace in await store.traces()]
        + [log.model_dump_json() for log in await store.logs()]
    )
    assert "raw-access-token" not in serialized
    assert "auth0:token-ref-secret" not in serialized
    assert "[REDACTED]" in serialized


def _auth0_session_response(monkeypatch, *, user_payload: dict[str, object]) -> httpx.Response:
    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            _ = args, kwargs

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            _ = exc_type, exc_value, traceback

        async def post(
            self,
            url: str,
            data: dict[str, str],
        ) -> httpx.Response:
            _ = data
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
            _ = headers
            return httpx.Response(200, request=httpx.Request("GET", url), json=user_payload)

    monkeypatch.setattr(routes.httpx, "AsyncClient", FakeAsyncClient)
    app = create_app(
        SupervisorSettings(
            auth0_domain="samples.auth0.com",
            auth0_audience="https://api.example.test",
            auth0_management_client_id="management-client-id",
            auth0_management_client_secret="management-secret",
            internal_service_auth_secret="test-internal-secret",
        )
    )
    with TestClient(app) as client:
        return client.post(
            "/identity/auth0/session",
            headers=_signed_context_headers(
                user_id="auth0|user-1",
                session_id="auth0-session-1",
                token_ref="auth0:sample",
                token_scopes=["openid", "profile"],
            ),
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


def _signed_context_headers(
    *,
    user_id: str = "auth0|user-1",
    session_id: str = "auth0-session-1",
    token_ref: str = "auth0:sample",
    token_scopes: list[str] | None = None,
    tenant_id: str | None = None,
) -> dict[str, str]:
    return signed_session_context_headers(
        TrustedSessionContext(
            allowed_tools=[],
            correlation_id="supervisor-test",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            session_id=session_id,
            tenant_id=tenant_id,
            token_ref=token_ref,
            token_scopes=token_scopes or [],
            user_id=user_id,
        ),
        secret="test-internal-secret",
    )

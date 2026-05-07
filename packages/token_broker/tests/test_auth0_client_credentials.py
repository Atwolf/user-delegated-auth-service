from __future__ import annotations

import json
from base64 import urlsafe_b64encode
from urllib.parse import parse_qs

import httpx
from token_broker import Auth0ClientCredentialsClient, Auth0ClientCredentialsConfig


async def test_auth0_client_credentials_exchange_posts_form_without_logging_secret() -> None:
    captured_body: bytes | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body
        captured_body = request.content
        return httpx.Response(
            200,
            json={
                "access_token": "issued-access-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "openid profile email",
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = Auth0ClientCredentialsClient(client=http_client)
    config = Auth0ClientCredentialsConfig(
        domain="https://samples.auth0.com/",
        token_endpoint="https://samples.auth0.com/oauth/token",
        jwks_endpoint="https://samples.auth0.com/.well-known/jwks.json",
        client_id="client-id",
        client_secret="client-secret",
        scopes=["openid", "profile", "email"],
        audience="https://api.example.test",
    )

    response = await client.exchange(config)

    assert response.access_token == "issued-access-token"
    assert response.expires_in == 3600
    assert response.scopes == ("openid", "profile", "email")
    assert response.audience == "https://api.example.test"
    assert response.token_ref.startswith("auth0:")
    assert "issued-access-token" not in repr(response)
    assert "client-secret" not in repr(config)

    assert captured_body is not None
    form = parse_qs(captured_body.decode("utf-8"))
    assert form["grant_type"] == ["client_credentials"]
    assert form["client_id"] == ["client-id"]
    assert form["client_secret"] == ["client-secret"]
    assert form["scope"] == ["openid profile email"]
    assert form["audience"] == ["https://api.example.test"]

    await http_client.aclose()


async def test_auth0_response_falls_back_to_requested_scopes_when_scope_missing() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "issued-access-token",
                "token_type": "Bearer",
                "expires_in": 60,
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = Auth0ClientCredentialsClient(client=http_client)
    config = Auth0ClientCredentialsConfig(
        domain="samples.auth0.com",
        token_endpoint="https://samples.auth0.com/oauth/token",
        jwks_endpoint="https://samples.auth0.com/.well-known/jwks.json",
        client_id="client-id",
        client_secret="client-secret",
        scopes=["read:reports"],
    )

    response = await client.exchange(config)

    assert response.scopes == ("read:reports",)

    await http_client.aclose()


async def test_auth0_response_uses_access_token_scope_claim_when_scope_missing() -> None:
    token = _unsigned_jwt({"scope": "read:users read:apps"})

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": 60,
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = Auth0ClientCredentialsClient(client=http_client)
    config = Auth0ClientCredentialsConfig(
        domain="samples.auth0.com",
        token_endpoint="https://samples.auth0.com/oauth/token",
        jwks_endpoint="https://samples.auth0.com/.well-known/jwks.json",
        client_id="client-id",
        client_secret="client-secret",
        scopes=[],
        audience="https://api.example.test",
    )

    response = await client.exchange(config)

    assert response.scopes == ("read:users", "read:apps")

    await http_client.aclose()


async def test_auth0_response_uses_access_token_permissions_when_scope_missing() -> None:
    token = _unsigned_jwt({"permissions": ["read:billing", "read:accounts"]})

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": 60,
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = Auth0ClientCredentialsClient(client=http_client)
    config = Auth0ClientCredentialsConfig(
        domain="samples.auth0.com",
        token_endpoint="https://samples.auth0.com/oauth/token",
        jwks_endpoint="https://samples.auth0.com/.well-known/jwks.json",
        client_id="client-id",
        client_secret="client-secret",
        scopes=[],
        audience="https://api.example.test",
    )

    response = await client.exchange(config)

    assert response.scopes == ("read:billing", "read:accounts")

    await http_client.aclose()


def _unsigned_jwt(claims: dict[str, object]) -> str:
    header = _base64url({"alg": "none", "typ": "JWT"})
    payload = _base64url(claims)
    return f"{header}.{payload}.signature"


def _base64url(payload: dict[str, object]) -> str:
    return urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")

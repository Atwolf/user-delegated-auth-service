from __future__ import annotations

import json
from base64 import urlsafe_b64decode
from binascii import Error as Base64DecodeError
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any, cast

import httpx

from token_broker.models import (
    ACCESS_TOKEN_TYPE,
    Auth0ClientCredentialsConfig,
    Auth0ClientCredentialsTokenResponse,
    Auth0OnBehalfOfConfig,
    WorkflowTokenExchangeRequest,
    WorkflowTokenExchangeResponse,
)


class Auth0ClientCredentialsClient:
    """Async Auth0 Client Credentials exchange client."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def exchange(
        self,
        config: Auth0ClientCredentialsConfig,
    ) -> Auth0ClientCredentialsTokenResponse:
        form_data: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": config.client_id,
            "client_secret": config.client_secret.get_secret_value(),
        }
        if config.audience:
            form_data["audience"] = config.audience
        if config.scopes:
            form_data["scope"] = " ".join(config.scopes)

        response = await self._client.post(config.token_endpoint, data=form_data)
        response.raise_for_status()
        payload = cast(dict[str, Any], response.json())
        access_token = _required_string(payload, "access_token")

        response_scopes = _scopes_from_response(
            payload=payload,
            access_token=access_token,
            requested_scopes=config.scopes,
        )

        expires_in = payload.get("expires_in")
        return Auth0ClientCredentialsTokenResponse.from_access_token(
            access_token=access_token,
            token_type=_required_string(payload, "token_type"),
            expires_in=expires_in if isinstance(expires_in, int) else None,
            scopes=response_scopes,
            audience=config.audience,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Auth0ClientCredentialsClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()


class Auth0OnBehalfOfClient:
    """Auth0 user-delegated token-exchange client."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def exchange_for_workflow_token(
        self,
        config: Auth0OnBehalfOfConfig,
        request: WorkflowTokenExchangeRequest,
    ) -> WorkflowTokenExchangeResponse:
        payload: dict[str, str] = {
            "client_id": config.client_id,
            "client_secret": config.client_secret.get_secret_value(),
            "subject_token": request.auth_context_ref,
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token_type": ACCESS_TOKEN_TYPE,
            "requested_token_type": ACCESS_TOKEN_TYPE,
            "audience": request.requested_audience or config.audience,
        }
        if request.requested_scopes:
            payload["scope"] = " ".join(request.requested_scopes)

        response = await self._client.post(config.token_endpoint, data=payload)
        response.raise_for_status()
        response_payload = cast(dict[str, Any], response.json())
        access_token = _required_string(response_payload, "access_token")
        expires_in = response_payload.get("expires_in")
        raw_scope = response_payload.get("scope")
        scopes = (
            _parse_scope_string(raw_scope)
            if isinstance(raw_scope, str) and raw_scope.strip()
            else tuple(request.requested_scopes)
        )
        return WorkflowTokenExchangeResponse(
            access_token=access_token,
            scopes=list(scopes),
            audience=request.requested_audience or config.audience,
            expires_at=_expires_at(expires_in if isinstance(expires_in, int) else None),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Auth0OnBehalfOfClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Auth0 token response missing required {key}")
    return value


def _parse_scope_string(value: str) -> tuple[str, ...]:
    return tuple(scope for scope in value.split(" ") if scope)


def _scopes_from_response(
    *,
    payload: dict[str, Any],
    access_token: str,
    requested_scopes: tuple[str, ...],
) -> tuple[str, ...]:
    raw_scope = payload.get("scope")
    if isinstance(raw_scope, str) and raw_scope.strip():
        return _parse_scope_string(raw_scope)

    token_scopes = _scopes_from_unverified_jwt(access_token)
    if token_scopes:
        return token_scopes

    return requested_scopes


def _scopes_from_unverified_jwt(access_token: str) -> tuple[str, ...]:
    parts = access_token.split(".")
    if len(parts) < 2:
        return ()

    try:
        payload_bytes = urlsafe_b64decode(_with_base64_padding(parts[1]))
        claims = json.loads(payload_bytes.decode("utf-8"))
    except (Base64DecodeError, UnicodeError, json.JSONDecodeError):
        return ()

    if not isinstance(claims, dict):
        return ()

    claim_values = cast(dict[str, object], claims)
    scopes: list[str] = []
    raw_scope = claim_values.get("scope")
    if isinstance(raw_scope, str) and raw_scope.strip():
        scopes.extend(_parse_scope_string(raw_scope))

    raw_permissions = claim_values.get("permissions")
    if isinstance(raw_permissions, list):
        permissions = cast(list[object], raw_permissions)
        scopes.extend(
            permission for permission in permissions if isinstance(permission, str)
        )

    return tuple(dict.fromkeys(scope.strip() for scope in scopes if scope.strip()))


def _with_base64_padding(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return f"{value}{padding}".encode("ascii")


def _expires_at(expires_in: int | None) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=expires_in or 3600)

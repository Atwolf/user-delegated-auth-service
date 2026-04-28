from __future__ import annotations

from types import TracebackType
from typing import Any, cast

import httpx

from token_broker.models import (
    Auth0ClientCredentialsConfig,
    Auth0ClientCredentialsTokenResponse,
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

        raw_scope = payload.get("scope")
        response_scopes = (
            _parse_scope_string(raw_scope)
            if isinstance(raw_scope, str) and raw_scope.strip()
            else config.scopes
        )

        expires_in = payload.get("expires_in")
        return Auth0ClientCredentialsTokenResponse.from_access_token(
            access_token=_required_string(payload, "access_token"),
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


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Auth0 token response missing required {key}")
    return value


def _parse_scope_string(value: str) -> tuple[str, ...]:
    return tuple(scope for scope in value.split(" ") if scope)

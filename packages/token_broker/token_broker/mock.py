from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from token_broker.models import (
    TokenExchangeRequest,
    TokenExchangeResponse,
    WorkflowTokenExchangeRequest,
    WorkflowTokenExchangeResponse,
)

AccessTokenFactory = Callable[[TokenExchangeRequest], str]


class MockTokenBrokerClient:
    """In-memory token broker client for tests and local wiring.

    The mock intentionally performs no logging. The returned access token is a
    raw string so callers exercise the same contract as the real token broker.
    """

    def __init__(
        self,
        access_token: str | AccessTokenFactory = "mock-access-token",
        *,
        expires_in: int | None = 3600,
    ) -> None:
        self._access_token = access_token
        self._expires_in = expires_in

    async def exchange_token(
        self,
        request: TokenExchangeRequest,
    ) -> TokenExchangeResponse:
        access_token = (
            self._access_token(request)
            if callable(self._access_token)
            else self._access_token
        )
        return TokenExchangeResponse(
            access_token=access_token,
            expires_in=self._expires_in,
            scopes=request.requested_scopes,
        )

    async def exchange_for_workflow_token(
        self,
        request: WorkflowTokenExchangeRequest,
    ) -> WorkflowTokenExchangeResponse:
        expires_in = request.ttl_seconds or self._expires_in or 3600
        access_token = (
            self._access_token
            if isinstance(self._access_token, str)
            else self._access_token(
                TokenExchangeRequest(
                    subject_token=request.auth_context_ref,
                    requested_scopes=tuple(request.requested_scopes or ["workflow"]),
                    audience=request.requested_audience,
                    actor=request.user_id,
                )
            )
        )
        return WorkflowTokenExchangeResponse(
            access_token=access_token,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            scopes=request.requested_scopes,
            audience=request.requested_audience,
        )

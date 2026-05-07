from __future__ import annotations

from typing import Protocol

from token_broker.models import (
    TokenExchangeRequest,
    TokenExchangeResponse,
    WorkflowTokenExchangeRequest,
    WorkflowTokenExchangeResponse,
)


class TokenBrokerClient(Protocol):
    async def exchange_token(
        self,
        request: TokenExchangeRequest,
    ) -> TokenExchangeResponse:
        """Exchange an incoming subject token for an access token."""
        ...

    async def exchange_for_workflow_token(
        self,
        request: WorkflowTokenExchangeRequest,
    ) -> WorkflowTokenExchangeResponse:
        """Exchange approved workflow scopes for a raw access token."""
        ...

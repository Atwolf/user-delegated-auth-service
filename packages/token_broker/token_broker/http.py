from __future__ import annotations

from types import TracebackType

import httpx

from token_broker.models import (
    TokenExchangeRequest,
    TokenExchangeResponse,
    WorkflowTokenExchangeRequest,
    WorkflowTokenExchangeResponse,
)


class HttpTokenBrokerClient:
    """Async HTTP token broker client scaffold backed by httpx.AsyncClient."""

    def __init__(
        self,
        *,
        base_url: str,
        endpoint: str = "/token/exchange",
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._endpoint = endpoint
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
        )

    async def exchange_token(
        self,
        request: TokenExchangeRequest,
    ) -> TokenExchangeResponse:
        response = await self._client.post(
            self._endpoint,
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        return TokenExchangeResponse.model_validate_json(response.content)

    async def exchange_for_workflow_token(
        self,
        request: WorkflowTokenExchangeRequest,
    ) -> WorkflowTokenExchangeResponse:
        response = await self._client.post(
            "/workflow/token/exchange",
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        return WorkflowTokenExchangeResponse.model_validate_json(response.content)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> HttpTokenBrokerClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

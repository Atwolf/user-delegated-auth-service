from __future__ import annotations

import os
from typing import Any, Protocol, cast

import httpx

DEFAULT_AGENT_SERVICE_URL = "http://agent-service:8090"


class AgentServiceClient(Protocol):
    async def plan_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the supervisor workflow manifest for an AG-UI run."""
        ...


class HttpAgentServiceClient:
    def __init__(
        self,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        configured_url = base_url or os.getenv("AGENT_SERVICE_URL") or DEFAULT_AGENT_SERVICE_URL
        self._base_url = configured_url.rstrip("/")
        self._http_client = http_client
        self._timeout = timeout

    async def plan_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._http_client is not None:
            response = await self._http_client.post("/workflows/plan", json=payload)
            response.raise_for_status()
            return cast(dict[str, Any], response.json())

        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.post("/workflows/plan", json=payload)
            response.raise_for_status()
            return cast(dict[str, Any], response.json())

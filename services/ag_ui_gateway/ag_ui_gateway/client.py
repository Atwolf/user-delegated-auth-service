from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any, Protocol, cast

import httpx

DEFAULT_AGENT_SERVICE_URL = "http://agent-service:8090"


class AgentServiceClient(Protocol):
    def stream_run(
        self,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream Agent Runtime events for an AG-UI run."""
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

    def stream_run(
        self,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        return self._stream_run(payload, headers or {})

    async def _stream_run(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> AsyncIterator[dict[str, Any]]:
        if self._http_client is not None:
            async with self._http_client.stream(
                "POST",
                "/runs/stream",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for event in _iter_sse_events(response):
                    yield event
            return

        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                "/runs/stream",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for event in _iter_sse_events(response):
                    yield event


async def _iter_sse_events(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    async for line in response.aiter_lines():
        if not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        if not payload:
            continue
        decoded = json.loads(payload)
        if isinstance(decoded, dict):
            yield cast(dict[str, Any], decoded)

from __future__ import annotations

from types import TracebackType

import httpx

from observability.models import WorkflowEvent


class ObservabilitySidecarClient:
    """Async client used by services to send traces and logs to the local sidecar."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:4319",
        client: httpx.AsyncClient | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)

    async def emit_trace(self, *, source_component: str, event: WorkflowEvent) -> None:
        response = await self._client.post(
            "/v1/traces",
            json={
                "source_component": source_component,
                "event": event.model_dump(mode="json"),
            },
        )
        response.raise_for_status()

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
        response = await self._client.post(
            "/v1/logs",
            json={
                "source_component": source_component,
                "level": level,
                "message": message,
                "attributes": attributes or {},
                "trace_id": trace_id,
                "agentic_span_id": agentic_span_id,
            },
        )
        response.raise_for_status()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> ObservabilitySidecarClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

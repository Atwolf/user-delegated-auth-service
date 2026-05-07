from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Iterable

from observability.models import WorkflowEvent
from observability.redaction import redact_sensitive

from observability_sidecar.models import AgenticTraceIngest, LogIngest, SidecarStats

logger = logging.getLogger("uvicorn.error")


class InMemoryTelemetryStore:
    """Bounded in-memory telemetry store for local tests and sidecar monitoring."""

    def __init__(self, *, max_items: int = 500) -> None:
        self._traces: deque[AgenticTraceIngest] = deque(maxlen=max_items)
        self._logs: deque[LogIngest] = deque(maxlen=max_items)
        self._lock = asyncio.Lock()

    async def append_trace(self, ingest: AgenticTraceIngest) -> AgenticTraceIngest:
        redacted_event = ingest.event.model_copy(
            update={"attributes": redact_sensitive(ingest.event.attributes)}
        )
        safe_ingest = ingest.model_copy(update={"event": redacted_event})
        async with self._lock:
            self._traces.append(safe_ingest)
            trace_count = len(self._traces)
        logger.info(
            "trace_ingested source_component=%s event_type=%s trace_count=%s",
            safe_ingest.source_component,
            safe_ingest.event.event_type,
            trace_count,
        )
        return safe_ingest

    async def append_log(self, ingest: LogIngest) -> LogIngest:
        safe_ingest = ingest.redacted()
        async with self._lock:
            self._logs.append(safe_ingest)
            log_count = len(self._logs)
        logger.info(
            "log_ingested source_component=%s level=%s log_count=%s",
            safe_ingest.source_component,
            safe_ingest.level,
            log_count,
        )
        return safe_ingest

    async def traces(self) -> list[AgenticTraceIngest]:
        async with self._lock:
            return list(self._traces)

    async def logs(self) -> list[LogIngest]:
        async with self._lock:
            return list(self._logs)

    async def stats(self) -> SidecarStats:
        async with self._lock:
            return SidecarStats(trace_count=len(self._traces), log_count=len(self._logs))

    async def event_types(self) -> list[str]:
        async with self._lock:
            return sorted({trace.event.event_type for trace in self._traces})

    async def components(self) -> list[str]:
        async with self._lock:
            names: Iterable[str] = (
                [trace.source_component for trace in self._traces]
                + [log.source_component for log in self._logs]
            )
            return sorted(set(names))


def workflow_event_from_log(log: LogIngest) -> WorkflowEvent:
    """Convert a log line into a workflow-shaped event for unified monitoring."""

    return WorkflowEvent(
        event_id=f"log:{log.source_component}:{log.created_at.isoformat()}",
        event_type=f"log.{log.level}",
        user_id="system",
        session_id="observability-sidecar",
        agentic_span_id=log.agentic_span_id or "log",
        trace_id=log.trace_id,
        agent_name=log.source_component,
        attributes={"message": log.message, **log.attributes},
        created_at=log.created_at,
    )

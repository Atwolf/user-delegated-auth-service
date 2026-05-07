from __future__ import annotations

from collections.abc import Mapping
from contextlib import nullcontext
from typing import Any, Protocol, runtime_checkable

from .models import WorkflowEvent
from .redaction import redact_sensitive


@runtime_checkable
class WorkflowEventEmitter(Protocol):
    async def emit_event(self, ctx: object, event: WorkflowEvent) -> None: ...

    def start_span(
        self,
        ctx: object,
        name: str,
        attributes: Mapping[str, object] | None = None,
    ) -> Any: ...


class NoopWorkflowEventEmitter:
    async def emit_event(self, ctx: object, event: WorkflowEvent) -> None:
        _ = ctx, event

    def start_span(
        self,
        ctx: object,
        name: str,
        attributes: Mapping[str, object] | None = None,
    ) -> Any:
        _ = ctx, name, redact_sensitive(attributes or {})
        return nullcontext()

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from typing import Any, cast

from .models import OtelAttributeValue, OtelScalar, WorkflowEvent, WorkflowOtelEvent
from .redaction import redact_sensitive

_RESERVED_EVENT_KEYS = {"event_type", "attributes"}


def _is_otel_scalar(value: object) -> bool:
    return isinstance(value, str | bool | int | float)


def _to_otel_value(value: object) -> OtelAttributeValue:
    if _is_otel_scalar(value):
        return cast(OtelAttributeValue, value)

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        scalar_values: list[OtelScalar] = []
        for item in cast(Sequence[object], value):
            if not _is_otel_scalar(item):
                break
            scalar_values.append(cast(OtelScalar, item))
        else:
            return scalar_values

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def workflow_event_to_otel(event: WorkflowEvent) -> WorkflowOtelEvent:
    payload = cast(
        dict[str, object],
        redact_sensitive(event.model_dump(mode="json", exclude_none=True)),
    )
    attributes: dict[str, OtelAttributeValue] = {}

    for key, value in payload.items():
        if key in _RESERVED_EVENT_KEYS:
            continue
        attributes[f"workflow.{key}"] = _to_otel_value(value)

    event_attributes = payload.get("attributes", {})
    if isinstance(event_attributes, Mapping):
        for key, value in cast(Mapping[str, object], event_attributes).items():
            attributes[f"workflow.attr.{key}"] = _to_otel_value(value)

    return WorkflowOtelEvent(name=event.event_type, attributes=attributes)


class OtelWorkflowEventEmitter:
    """Minimal OTEL adapter that only exposes redacted, attribute-safe payloads."""

    def __init__(
        self,
        *,
        tracer: object | None = None,
        event_logger: Callable[[str, Mapping[str, OtelAttributeValue]], None] | None = None,
    ) -> None:
        self._tracer = tracer
        self._event_logger = event_logger
        self.emitted_events: list[WorkflowOtelEvent] = []

    async def emit_event(self, ctx: object, event: WorkflowEvent) -> None:
        _ = ctx
        otel_event = workflow_event_to_otel(event)
        self.emitted_events.append(otel_event)

        if self._event_logger is not None:
            self._event_logger(otel_event.name, otel_event.attributes)

    def start_span(
        self,
        ctx: object,
        name: str,
        attributes: Mapping[str, object] | None = None,
    ) -> Any:
        _ = ctx
        safe_attributes = {
            str(key): _to_otel_value(value)
            for key, value in redact_sensitive(attributes or {}).items()
        }

        start_span = getattr(self._tracer, "start_as_current_span", None)
        if callable(start_span):
            return start_span(name, attributes=safe_attributes)

        return nullcontext()

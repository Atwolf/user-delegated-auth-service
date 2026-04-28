from __future__ import annotations

import pytest
from observability.models import WorkflowEvent
from observability.otel import OtelWorkflowEventEmitter, workflow_event_to_otel
from observability.redaction import REDACTED


def test_workflow_event_to_otel_redacts_nested_attributes() -> None:
    event = WorkflowEvent(
        event_id="evt-1",
        event_type="workflow.token_exchanged",
        user_id="user-1",
        session_id="session-1",
        workflow_id="workflow-1",
        agentic_span_id="span-1",
        attributes={
            "access_token": "raw-access-token",
            "headers": {"Authorization": "Bearer raw-header-token"},
            "safe": "kept",
        },
    )

    otel_event = workflow_event_to_otel(event)

    assert otel_event.name == "workflow.token_exchanged"
    assert otel_event.attributes["workflow.event_id"] == "evt-1"
    assert otel_event.attributes["workflow.attr.access_token"] == REDACTED
    assert "raw-header-token" not in str(otel_event.attributes["workflow.attr.headers"])
    assert REDACTED in str(otel_event.attributes["workflow.attr.headers"])
    assert otel_event.attributes["workflow.attr.safe"] == "kept"


@pytest.mark.asyncio
async def test_otel_emitter_keeps_redacted_event_payload() -> None:
    captured: list[tuple[str, object]] = []
    emitter = OtelWorkflowEventEmitter(
        event_logger=lambda name, attributes: captured.append((name, attributes)),
    )
    event = WorkflowEvent(
        event_id="evt-1",
        event_type="workflow.step_started",
        user_id="user-1",
        session_id="session-1",
        workflow_id="workflow-1",
        agentic_span_id="span-1",
        attributes={"authToken": "raw-auth-token"},
    )

    await emitter.emit_event(None, event)

    assert len(emitter.emitted_events) == 1
    assert captured[0][0] == "workflow.step_started"
    assert emitter.emitted_events[0].attributes["workflow.attr.authToken"] == REDACTED

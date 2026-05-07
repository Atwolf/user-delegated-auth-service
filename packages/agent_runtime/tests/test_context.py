from __future__ import annotations

import pytest
from agent_runtime.context import AgentInvocationContext
from agent_runtime.interfaces import AgentHandler
from pydantic import ValidationError


def valid_context() -> dict[str, object]:
    return {
        "user_id": "user-1",
        "session_id": "session-1",
        "agentic_span_id": "span-1",
        "calling_agent": "supervisor",
        "target_agent": "planner",
        "auth_context_ref": "auth-context-1",
        "idempotency_key": "idem-1",
    }


def test_agent_invocation_context_accepts_required_contract_fields() -> None:
    ctx = AgentInvocationContext.model_validate(valid_context())

    assert ctx.user_id == "user-1"
    assert ctx.calling_agent == "supervisor"
    assert ctx.target_agent == "planner"


def test_agent_invocation_context_rejects_empty_required_fields() -> None:
    raw = valid_context()
    raw["target_agent"] = ""

    with pytest.raises(ValidationError):
        AgentInvocationContext.model_validate(raw)


def test_agent_invocation_context_rejects_unknown_fields() -> None:
    raw = valid_context()
    raw["unexpected"] = "value"

    with pytest.raises(ValidationError):
        AgentInvocationContext.model_validate(raw)


def test_agent_handler_protocol_imports_without_runtime_a2a_dependency() -> None:
    assert AgentHandler is not None

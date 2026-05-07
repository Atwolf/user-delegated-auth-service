from __future__ import annotations

import pytest
from a2a_runtime.errors import UnknownA2AActionError
from a2a_runtime.models import StrictA2APayload
from a2a_runtime.validation import (
    ActionPayloadContracts,
    validate_envelope_for_action,
    validate_payload_for_action,
)
from pydantic import ValidationError


class ToolProposalPayload(StrictA2APayload):
    tool_name: str
    arguments: dict[str, object]
    priority: int


class ApprovalDecisionPayload(StrictA2APayload):
    approved: bool
    approval_id: str


CONTRACTS: ActionPayloadContracts = {
    "tool.propose": ToolProposalPayload,
    "approval.decide": ApprovalDecisionPayload,
}


def envelope(payload: dict[str, object]) -> dict[str, object]:
    return {
        "message_id": "msg-1",
        "idempotency_key": "idem-1",
        "from_agent": "supervisor",
        "to_agent": "planner",
        "user_id": "user-1",
        "session_id": "session-1",
        "agentic_span_id": "span-1",
        "auth_context_ref": "auth-context-1",
        "payload": payload,
    }


def test_validate_payload_for_action_uses_action_specific_contract() -> None:
    payload = validate_payload_for_action(
        "tool.propose",
        {"tool_name": "get_app", "arguments": {"appid": "ABCD"}, "priority": 10},
        CONTRACTS,
    )

    assert isinstance(payload, ToolProposalPayload)
    assert payload.tool_name == "get_app"


def test_validate_envelope_for_action_returns_typed_payload() -> None:
    validated = validate_envelope_for_action(
        "approval.decide",
        envelope({"approved": True, "approval_id": "approval-1"}),
        CONTRACTS,
    )

    assert isinstance(validated.payload, ApprovalDecisionPayload)
    assert validated.payload.approved is True


def test_validate_envelope_for_action_rejects_extra_payload_fields() -> None:
    with pytest.raises(ValidationError):
        validate_envelope_for_action(
            "tool.propose",
            envelope(
                {
                    "tool_name": "get_app",
                    "arguments": {"appid": "ABCD"},
                    "priority": 10,
                    "unexpected": "not allowed",
                }
            ),
            CONTRACTS,
        )


def test_validate_envelope_for_action_rejects_coerced_payload_types() -> None:
    with pytest.raises(ValidationError):
        validate_envelope_for_action(
            "tool.propose",
            envelope(
                {
                    "tool_name": "get_app",
                    "arguments": {"appid": "ABCD"},
                    "priority": "10",
                }
            ),
            CONTRACTS,
        )


def test_validate_envelope_for_action_rejects_wrong_action_payload_shape() -> None:
    with pytest.raises(ValidationError):
        validate_envelope_for_action(
            "approval.decide",
            envelope({"tool_name": "get_app", "arguments": {}, "priority": 10}),
            CONTRACTS,
        )


def test_validate_envelope_for_action_rejects_unknown_actions() -> None:
    with pytest.raises(UnknownA2AActionError):
        validate_envelope_for_action(
            "not.registered",
            envelope({"tool_name": "get_app", "arguments": {}, "priority": 10}),
            CONTRACTS,
        )

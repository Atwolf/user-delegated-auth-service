from __future__ import annotations

import pytest
from a2a_runtime.models import A2AEnvelope, StrictA2APayload
from pydantic import ValidationError


class ProposalPayload(StrictA2APayload):
    request: str


def valid_envelope(payload: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "message_id": "msg-1",
        "idempotency_key": "idem-1",
        "from_agent": "supervisor",
        "to_agent": "planner",
        "user_id": "user-1",
        "session_id": "session-1",
        "agentic_span_id": "span-1",
        "auth_context_ref": "auth-context-1",
        "payload": payload or {"request": "plan this"},
    }


def test_valid_typed_a2a_envelope_accepts_required_contract_fields() -> None:
    envelope = A2AEnvelope[ProposalPayload].model_validate(valid_envelope())

    assert envelope.message_id == "msg-1"
    assert isinstance(envelope.payload, ProposalPayload)
    assert envelope.payload.request == "plan this"


def test_a2a_envelope_rejects_missing_required_fields() -> None:
    raw = valid_envelope()
    del raw["message_id"]

    with pytest.raises(ValidationError):
        A2AEnvelope[ProposalPayload].model_validate(raw)


def test_a2a_envelope_rejects_empty_required_fields() -> None:
    raw = valid_envelope()
    raw["auth_context_ref"] = ""

    with pytest.raises(ValidationError):
        A2AEnvelope[ProposalPayload].model_validate(raw)


def test_a2a_envelope_rejects_unknown_top_level_fields() -> None:
    raw = valid_envelope()
    raw["unexpected"] = "value"

    with pytest.raises(ValidationError):
        A2AEnvelope[ProposalPayload].model_validate(raw)

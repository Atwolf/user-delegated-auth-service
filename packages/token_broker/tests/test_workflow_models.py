from __future__ import annotations

import pytest
from pydantic import ValidationError
from token_broker import WorkflowTokenExchangeRequest, WorkflowTokenExchangeResponse


def test_workflow_token_request_deduplicates_and_sorts_scopes() -> None:
    request = WorkflowTokenExchangeRequest(
        user_id="user-1",
        session_id="session-1",
        workflow_id="workflow-1",
        approval_id="approval-1",
        plan_hash="sha256:abc",
        auth_context_ref="auth-1",
        requested_scopes=["DOE.Billing.XYZ", "DOE.Developer.ABCD", "DOE.Billing.XYZ"],
    )

    assert request.requested_scopes == ["DOE.Billing.XYZ", "DOE.Developer.ABCD"]


def test_workflow_token_request_rejects_invalid_ttl() -> None:
    with pytest.raises(ValidationError):
        WorkflowTokenExchangeRequest(
            user_id="user-1",
            session_id="session-1",
            workflow_id="workflow-1",
            approval_id="approval-1",
            plan_hash="sha256:abc",
            auth_context_ref="auth-1",
            ttl_seconds=0,
        )


def test_workflow_token_response_returns_raw_token_but_masks_repr() -> None:
    response = WorkflowTokenExchangeResponse(access_token="raw-access-token")

    assert response.access_token == "raw-access-token"
    assert response.model_dump()["access_token"] == "raw-access-token"
    assert "raw-access-token" not in repr(response)

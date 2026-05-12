from __future__ import annotations

import pytest
from pydantic import ValidationError
from session_state.models import (
    AgUiThreadState,
    SessionState,
    WorkflowPlan,
    WorkflowState,
    WorkflowStatus,
    WorkflowStep,
)
from workflow_core import WorkflowPlan as CoreWorkflowPlan
from workflow_core import WorkflowStatus as CoreWorkflowStatus
from workflow_core import WorkflowStep as CoreWorkflowStep


def test_session_state_requires_strict_fields() -> None:
    with pytest.raises(ValidationError):
        SessionState(
            user_id=123,
            session_id="session-1",
        )

    with pytest.raises(ValidationError):
        SessionState(
            user_id="user-1",
            session_id="session-1",
            version=-1,
        )


def test_session_state_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SessionState(
            user_id="user-1",
            session_id="session-1",
            unexpected="value",
        )


def test_session_state_round_trips_as_pydantic_json_blob() -> None:
    state = SessionState(
        tenant_id="tenant-1",
        user_id="user-1",
        session_id="session-1",
        token_ref="token-ref",
        auth_context_ref="auth-ref",
        values={"selected_app": "ABCD"},
    )

    restored = SessionState.model_validate_json(state.model_dump_json())

    assert restored.model_dump() == state.model_dump()
    assert restored.auth_context_ref is None
    assert "auth_context_ref" not in state.model_dump()


def test_session_state_keeps_auth_context_ref_server_side_only() -> None:
    state = SessionState(
        user_id="user-1",
        session_id="session-1",
        token_ref="token-ref",
        auth_context_ref="raw-auth-ref",
    )

    assert state.auth_context_ref == "raw-auth-ref"
    assert state.model_dump() == {
        "tenant_id": None,
        "user_id": "user-1",
        "session_id": "session-1",
        "token_ref": "token-ref",
        "active_workflow_id": None,
        "version": 0,
        "values": {},
        "created_at": state.created_at,
        "updated_at": state.updated_at,
    }


def test_ag_ui_thread_state_round_trips_without_raw_auth_context() -> None:
    state = AgUiThreadState(
        tenant_id="tenant-1",
        user_id="user-1",
        session_id="session-1",
        thread_id="thread-1",
        messages=[{"role": "user", "content": "Check DNS"}],
        state={"token_ref": "token-ref", "workflow": {"workflow_id": "wf-1"}},
        token_ref="token-ref",
        auth_context_ref="raw-auth-ref",
        active_workflow_id="wf-1",
    )

    restored = AgUiThreadState.model_validate_json(state.model_dump_json())

    assert restored.model_dump() == state.model_dump()
    assert restored.auth_context_ref is None
    assert "auth_context_ref" not in state.model_dump()


def test_workflow_state_requires_status() -> None:
    with pytest.raises(ValidationError):
        WorkflowState(
            user_id="user-1",
            session_id="session-1",
            workflow_id="workflow-1",
        )


def test_workflow_state_rejects_invalid_status_literal() -> None:
    with pytest.raises(ValidationError):
        WorkflowState(
            user_id="user-1",
            session_id="session-1",
            workflow_id="workflow-1",
            status={"status": "paused"},
        )


def test_workflow_state_validates_nested_plan_strictly() -> None:
    with pytest.raises(ValidationError):
        WorkflowState(
            user_id="user-1",
            session_id="session-1",
            workflow_id="workflow-1",
            status={"status": "planned"},
            plan={
                "workflow_id": "workflow-1",
                "user_id": "user-1",
                "session_id": "session-1",
                "steps": [],
                "unexpected": "value",
            },
        )


def test_workflow_state_round_trips_as_pydantic_json_blob() -> None:
    plan = WorkflowPlan(
        workflow_id="workflow-1",
        user_id="user-1",
        session_id="session-1",
        steps=[
            WorkflowStep(
                step_id="step-1",
                target_agent="planner",
                action="plan",
                input_model_type="PlanRequest",
                input_payload_json="{}",
                required_scopes=["DOE.Developer.ABCD"],
            )
        ],
    )
    state = WorkflowState(
        user_id="user-1",
        session_id="session-1",
        workflow_id="workflow-1",
        plan=plan,
        status=WorkflowStatus(status="planned"),
    )

    assert WorkflowState.model_validate_json(state.model_dump_json()) == state


def test_workflow_state_accepts_canonical_workflow_core_models() -> None:
    plan = CoreWorkflowPlan(
        workflow_id="workflow-1",
        user_id="user-1",
        session_id="session-1",
        steps=[
            CoreWorkflowStep(
                step_id="step-1",
                target_agent="planner",
                action="plan",
                input_model_type="PlanRequest",
                input_payload_json="{}",
            )
        ],
    )
    state = WorkflowState(
        user_id="user-1",
        session_id="session-1",
        workflow_id="workflow-1",
        plan=plan,
        status=CoreWorkflowStatus(status="planned"),
    )

    assert state.plan == plan
    assert state.status == CoreWorkflowStatus(status="planned")

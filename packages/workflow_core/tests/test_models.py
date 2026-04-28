from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from workflow_core.models import (
    ApprovedWorkflow,
    AuthorizationBundle,
    ScopeRequirement,
    ToolProposal,
    WorkflowPlan,
    WorkflowStatus,
    WorkflowStep,
)


def test_tool_proposal_forbids_extra_fields_and_empty_names() -> None:
    with pytest.raises(ValidationError):
        ToolProposal(
            agent_name="developer",
            tool_name="get_developer_app",
            unexpected="nope",
        )

    with pytest.raises(ValidationError):
        ToolProposal(agent_name="", tool_name="get_developer_app")

    with pytest.raises(ValidationError):
        ToolProposal(agent_name="developer", tool_name="get_developer_app", arguments={"": 1})


def test_workflow_step_uses_strict_bool_validation() -> None:
    with pytest.raises(ValidationError):
        WorkflowStep(
            step_id="step-1",
            target_agent="developer",
            action="get_developer_app",
            input_model_type="DeveloperAppRequest",
            input_payload_json='{"appid":"ABCD"}',
            mutates_external_state=1,
        )


def test_workflow_models_normalize_scope_lists() -> None:
    bundle = AuthorizationBundle(
        workflow_id="workflow-1",
        scopes=["DOE.Developer.write", "DOE.Developer.read", "DOE.Developer.read"],
    )
    approved = ApprovedWorkflow(
        workflow_id="workflow-1",
        approval_id="approval-1",
        plan_hash="sha256:abc",
        approved_by_user_id="user-1",
        approved_scopes=[
            "DOE.Developer.write",
            "DOE.Developer.read",
            "DOE.Developer.write",
        ],
    )

    assert bundle.scopes == ["DOE.Developer.read", "DOE.Developer.write"]
    assert approved.approved_scopes == ["DOE.Developer.read", "DOE.Developer.write"]

    with pytest.raises(ValidationError):
        AuthorizationBundle(workflow_id="workflow-1", scopes=[""])

    with pytest.raises(ValidationError):
        ScopeRequirement(
            scope_template="DOE.Developer.{appid}",
            scope_args=[""],
            op="READ",
            hitl_description="Read app metadata",
        )


def test_workflow_plan_validates_required_fields_and_status_literals() -> None:
    step = WorkflowStep(
        step_id="step-1",
        target_agent="developer",
        action="get_developer_app",
        input_model_type="DeveloperAppRequest",
        input_payload_json='{"appid":"ABCD"}',
    )
    plan = WorkflowPlan(
        workflow_id="workflow-1",
        user_id="user-1",
        session_id="session-1",
        created_at=datetime(2026, 4, 27, tzinfo=UTC),
        steps=[step],
    )

    assert plan.steps == [step]
    assert WorkflowStatus(status="planned").status == "planned"

    with pytest.raises(ValidationError):
        WorkflowStatus(status="unknown")

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from workflow_core.models import (
    ApprovedWorkflow,
    AuthorizationBundle,
    EgressRequest,
    ScopeRequirement,
    ToolIntent,
    ToolProposal,
    WorkflowPlan,
    WorkflowPolicyDecision,
    WorkflowStatus,
    WorkflowStep,
)
from workflow_core.policy import evaluate_workflow_policy


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


def test_target_runtime_boundary_models_are_strict() -> None:
    intent = ToolIntent(
        agent_name="network_services_agent",
        mcp_server="network-mcp",
        tool_name="inspect_dns_record",
        arguments={"record_name": "app.example.com"},
        metadata_ref="tool_catalog:inspect_dns_record",
    )
    egress = EgressRequest(
        primitive="READ",
        method="GET",
        target_mcp="network-mcp",
        tool_name="inspect_dns_record",
        arguments={"record_name": "app.example.com"},
        workflow_id="workflow-1",
        obo_token_ref="obo:abc",
    )

    assert intent.metadata_ref == "tool_catalog:inspect_dns_record"
    assert egress.primitive == "READ"

    with pytest.raises(ValidationError):
        ToolIntent(
            agent_name="network_services_agent",
            mcp_server="network-mcp",
            tool_name="inspect_dns_record",
            arguments={"": "bad"},
            metadata_ref="tool_catalog:inspect_dns_record",
        )

    with pytest.raises(ValidationError):
        EgressRequest(
            primitive="MUTATION",
            method="PATCH",
            target_mcp="network-mcp",
            tool_name="inspect_dns_record",
            workflow_id="workflow-1",
        )


def test_policy_decision_requires_hitl_for_blast_radius() -> None:
    read_step = WorkflowStep(
        step_id="step-1",
        target_agent="network_services_agent",
        action="inspect_dns_record",
        input_model_type="inspect_dns_record.arguments",
        input_payload_json='{"record_name":"app.example.com"}',
        required_scopes=["read:dns:app.example.com"],
        operation_type="READ",
        blast_radius="low",
        hitl_description="Inspect DNS record",
    )
    write_step = WorkflowStep(
        step_id="step-2",
        target_agent="cloud_operations_agent",
        action="restart_vm",
        input_model_type="restart_vm.arguments",
        input_payload_json='{"vm_id":"vm-1"}',
        required_scopes=["write:vm:vm-1"],
        operation_type="WRITE",
        blast_radius="medium",
        hitl_description="Restart VM",
        mutates_external_state=True,
    )

    read_decision = evaluate_workflow_policy([read_step])
    write_decision = evaluate_workflow_policy([read_step, write_step])
    explicit_decision = WorkflowPolicyDecision(
        requires_hitl=True,
        blast_radius="high",
        human_description="Admin operation",
        required_scopes=["admin:iam:alice", "admin:iam:alice"],
    )

    assert read_decision.requires_hitl is False
    assert write_decision.requires_hitl is True
    assert write_decision.blast_radius == "medium"
    assert write_decision.required_scopes == ["read:dns:app.example.com", "write:vm:vm-1"]
    assert explicit_decision.required_scopes == ["admin:iam:alice"]

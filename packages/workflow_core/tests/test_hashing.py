from __future__ import annotations

from datetime import UTC, datetime

from workflow_core.hashing import canonical_json, plan_hash
from workflow_core.models import WorkflowPlan, WorkflowStep


def test_canonical_json_is_deterministic_and_excludes_none() -> None:
    created_at = datetime(2026, 4, 27, tzinfo=UTC)
    plan = WorkflowPlan(
        workflow_id="workflow-1",
        user_id="user-1",
        session_id="session-1",
        tenant_id=None,
        created_at=created_at,
        steps=[
            WorkflowStep(
                step_id="step-1",
                target_agent="developer",
                action="get_developer_app",
                input_model_type="DeveloperAppRequest",
                input_payload_json='{"appid":"ABCD"}',
                required_scopes=["DOE.Developer.ABCD"],
                downstream_audience=None,
            )
        ],
    )

    assert canonical_json(plan) == (
        '{"created_at":"2026-04-27T00:00:00Z",'
        '"session_id":"session-1",'
        '"steps":[{"action":"get_developer_app",'
        '"blast_radius":"low",'
        '"hitl_description":"Review workflow step before execution",'
        '"input_model_type":"DeveloperAppRequest",'
        '"input_payload_json":"{\\"appid\\":\\"ABCD\\"}",'
        '"mutates_external_state":false,'
        '"operation_type":"READ",'
        '"required_scopes":["DOE.Developer.ABCD"],'
        '"step_id":"step-1",'
        '"target_agent":"developer"}],'
        '"user_id":"user-1",'
        '"workflow_id":"workflow-1"}'
    )


def test_plan_hash_is_stable_for_equivalent_scope_sets() -> None:
    created_at = datetime(2026, 4, 27, 12, 30, tzinfo=UTC)
    common = {
        "workflow_id": "workflow-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "created_at": created_at,
    }
    first = WorkflowPlan(
        **common,
        steps=[
            WorkflowStep(
                step_id="step-1",
                target_agent="developer",
                action="get_developer_app",
                input_model_type="DeveloperAppRequest",
                input_payload_json='{"appid":"ABCD"}',
                required_scopes=["DOE.Developer.write", "DOE.Developer.read"],
            )
        ],
    )
    second = WorkflowPlan(
        **common,
        steps=[
            WorkflowStep(
                step_id="step-1",
                target_agent="developer",
                action="get_developer_app",
                input_model_type="DeveloperAppRequest",
                input_payload_json='{"appid":"ABCD"}',
                required_scopes=[
                    "DOE.Developer.read",
                    "DOE.Developer.write",
                    "DOE.Developer.read",
                ],
            )
        ],
    )

    assert first.steps[0].required_scopes == [
        "DOE.Developer.read",
        "DOE.Developer.write",
    ]
    assert plan_hash(first) == plan_hash(second)
    assert plan_hash(first).startswith("sha256:")

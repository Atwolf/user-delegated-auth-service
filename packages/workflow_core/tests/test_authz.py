from __future__ import annotations

import pytest
from workflow_core.authz import (
    ScopeMaterializationError,
    get_workflow_authz_metadata,
    materialize_scopes,
    materialize_scopes_for_proposal,
    restricted,
    scope_requirements_from_callable,
)
from workflow_core.models import ScopeRequirement, ToolProposal


def test_restricted_attaches_metadata_and_builds_scope_requirements() -> None:
    @restricted(
        scopes=["DOE.Developer.{appid}", "DOE.Developer.read"],
        args="appid",
        op="READ",
        hitl="Read developer app metadata",
    )
    async def get_developer_app(appid: str) -> dict[str, str]:
        return {"appid": appid}

    assert get_workflow_authz_metadata(get_developer_app) == {
        "scopes": ["DOE.Developer.{appid}", "DOE.Developer.read"],
        "scope_args": ["appid"],
        "op": "READ",
        "hitl": "Read developer app metadata",
    }

    requirements = scope_requirements_from_callable(get_developer_app)

    assert requirements == [
        ScopeRequirement(
            scope_template="DOE.Developer.{appid}",
            scope_args=["appid"],
            op="READ",
            hitl_description="Read developer app metadata",
        ),
        ScopeRequirement(
            scope_template="DOE.Developer.read",
            scope_args=["appid"],
            op="READ",
            hitl_description="Read developer app metadata",
        ),
    ]


def test_materialize_scopes_renders_templates_from_tool_arguments() -> None:
    proposal = ToolProposal(
        agent_name="developer",
        tool_name="get_developer_app",
        arguments={"appid": "ABCD"},
    )
    requirements = [
        ScopeRequirement(
            scope_template="DOE.Developer.{appid}",
            scope_args=["appid"],
            op="READ",
            hitl_description="Read app metadata",
        )
    ]

    assert materialize_scopes_for_proposal(proposal, requirements) == [
        "DOE.Developer.ABCD"
    ]


def test_materialize_scopes_dedupes_and_sorts() -> None:
    requirements = [
        ScopeRequirement(
            scope_template="DOE.Developer.{appid}",
            scope_args=["appid"],
            op="READ",
            hitl_description="Read app metadata",
        ),
        ScopeRequirement(
            scope_template="DOE.Billing.{account_id}",
            scope_args=["account_id"],
            op="READ",
            hitl_description="Read billing metadata",
        ),
        ScopeRequirement(
            scope_template="DOE.Developer.{appid}",
            scope_args=["appid"],
            op="READ",
            hitl_description="Read app metadata",
        ),
    ]

    assert materialize_scopes(
        requirements,
        {"appid": "ZZZ", "account_id": "123"},
    ) == ["DOE.Billing.123", "DOE.Developer.ZZZ"]


def test_materialize_scope_rejects_missing_or_non_scalar_arguments() -> None:
    requirement = ScopeRequirement(
        scope_template="DOE.Developer.{appid}",
        scope_args=["appid"],
        op="READ",
        hitl_description="Read app metadata",
    )

    with pytest.raises(ScopeMaterializationError, match="missing required"):
        materialize_scopes([requirement], {})

    with pytest.raises(ScopeMaterializationError, match="must be a string"):
        materialize_scopes([requirement], {"appid": {"nested": "value"}})


def test_materialize_scope_rejects_unsupported_template_syntax() -> None:
    requirement = ScopeRequirement(
        scope_template="DOE.Developer.{appid!r}",
        scope_args=["appid"],
        op="READ",
        hitl_description="Read app metadata",
    )

    with pytest.raises(ScopeMaterializationError, match="unsupported"):
        materialize_scopes([requirement], {"appid": "ABCD"})

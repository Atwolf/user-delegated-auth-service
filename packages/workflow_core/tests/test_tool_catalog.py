from __future__ import annotations

from workflow_core.tool_catalog import (
    get_tool_authorization,
    scope_requirements_for_auth0_token,
    scope_requirements_for_tool,
    select_auth0_scopes_for_tool,
)


def test_known_tool_authorization_metadata_is_centralized() -> None:
    authz = get_tool_authorization("get_developer_app")

    assert authz.auth0_scope_candidates == (
        "read:developer_apps",
        "read:apps",
        "read:developer",
    )
    assert authz.hitl_description == "Read developer app metadata for selected app ID"


def test_unknown_tool_uses_inspect_scope_requirement() -> None:
    requirements = scope_requirements_for_tool("unregistered_tool")

    assert len(requirements) == 1
    assert requirements[0].scope_template == "read:workflow"
    assert requirements[0].hitl_description == "Inspect the user request for workflow planning"


def test_auth0_issued_scopes_are_selected_for_known_tool() -> None:
    assert select_auth0_scopes_for_tool(
        "get_developer_app",
        ["read:users", "read:apps", "read:billing"],
    ) == ["read:apps"]


def test_auth0_issued_scopes_are_preserved_when_tenant_uses_custom_names() -> None:
    assert select_auth0_scopes_for_tool(
        "get_developer_app",
        ["apps:read", "tenant:workflow"],
    ) == ["apps:read", "tenant:workflow"]


def test_auth0_scope_requirements_use_issued_token_scopes() -> None:
    requirements = scope_requirements_for_auth0_token(
        "get_identity_profile",
        ["profile", "custom:permission"],
    )

    assert [requirement.scope_template for requirement in requirements] == ["profile"]
    assert requirements[0].scope_args == []

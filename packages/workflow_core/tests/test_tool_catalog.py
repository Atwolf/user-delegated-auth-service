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
    assert authz.workflow_scope_templates == ("read:client:{appid}",)
    assert authz.scope_args == ("appid",)
    assert authz.has_dynamic_workflow_scopes is True
    assert authz.hitl_description == "Read developer app metadata for selected app ID"
    assert authz.blast_radius == "low"


def test_unknown_tool_uses_inspect_scope_requirement() -> None:
    requirements = scope_requirements_for_tool("unregistered_tool")

    assert len(requirements) == 1
    assert requirements[0].scope_template == "read:workflow"
    assert requirements[0].scope_args == []
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


def test_auth0_known_dynamic_scopes_use_workflow_scope_templates() -> None:
    requirements = scope_requirements_for_auth0_token(
        "get_identity_profile",
        ["profile", "custom:permission"],
    )

    assert [requirement.scope_template for requirement in requirements] == [
        "read:user:{subject_user_id}"
    ]
    assert requirements[0].scope_args == ["subject_user_id"]


def test_auth0_known_static_scopes_preserve_issued_token_scope() -> None:
    requirements = scope_requirements_for_auth0_token(
        "propose_workflow_plan",
        ["read:workflow"],
    )

    assert [requirement.scope_template for requirement in requirements] == [
        "read:workflow"
    ]
    assert requirements[0].scope_args == []


def test_auth0_custom_scopes_are_preserved_when_no_known_candidate_matches() -> None:
    requirements = scope_requirements_for_auth0_token(
        "get_identity_profile",
        ["custom:permission"],
    )

    assert [requirement.scope_template for requirement in requirements] == [
        "custom:permission"
    ]
    assert requirements[0].scope_args == []


def test_network_and_cloud_tool_authorization_metadata() -> None:
    firewall = get_tool_authorization("update_firewall_rule")
    vm = get_tool_authorization("restart_vm")

    assert firewall.op == "WRITE"
    assert firewall.blast_radius == "high"
    assert firewall.downstream_audience == "network-mcp"
    assert firewall.workflow_scope_templates == ("write:firewall:{rule_id}",)

    assert vm.op == "WRITE"
    assert vm.blast_radius == "medium"
    assert vm.downstream_audience == "cloud-mcp"
    assert vm.workflow_scope_templates == ("write:vm:{vm_id}",)

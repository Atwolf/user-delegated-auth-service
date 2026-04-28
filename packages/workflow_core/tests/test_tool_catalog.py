from __future__ import annotations

from workflow_core.tool_catalog import (
    get_tool_authorization,
    scope_requirements_for_tool,
)


def test_known_tool_authorization_metadata_is_centralized() -> None:
    authz = get_tool_authorization("get_developer_app")

    assert authz.scope_template == "DOE.Developer.{appid}"
    assert authz.scope_args == ("appid",)
    assert authz.runtime_scopes == ("DOE.Developer.read",)
    assert authz.hitl_description == "Read developer app metadata for selected app ID"


def test_unknown_tool_uses_inspect_scope_requirement() -> None:
    requirements = scope_requirements_for_tool("unregistered_tool")

    assert len(requirements) == 1
    assert requirements[0].scope_template == "DOE.Workflow.inspect"
    assert requirements[0].hitl_description == "Inspect the user request for workflow planning"

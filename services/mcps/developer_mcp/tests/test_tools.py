from __future__ import annotations

from developer_mcp.tools import get_developer_app, get_workflow_authz


def test_developer_tool_declares_workflow_authz_metadata() -> None:
    metadata = get_workflow_authz(get_developer_app)

    assert metadata == {
        "scopes": ["read:client:{appid}"],
        "scope_args": ["appid"],
        "op": "READ",
        "hitl": "Read developer app metadata for selected app ID",
    }

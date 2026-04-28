from __future__ import annotations

from identity_mcp.tools import get_identity_profile, get_workflow_authz


def test_identity_tool_declares_workflow_authz_metadata() -> None:
    metadata = get_workflow_authz(get_identity_profile)

    assert metadata == {
        "scopes": ["read:identity", "read:users", "profile", "email"],
        "scope_args": [],
        "op": "READ",
        "hitl": "Read identity profile for selected user ID",
    }

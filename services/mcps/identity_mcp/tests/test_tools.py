from __future__ import annotations

from identity_mcp.tools import get_identity_profile, get_workflow_authz


def test_identity_tool_declares_workflow_authz_metadata() -> None:
    metadata = get_workflow_authz(get_identity_profile)

    assert metadata == {
        "scopes": ["read:user:{subject_user_id}"],
        "scope_args": ["subject_user_id"],
        "op": "READ",
        "hitl": "Read identity profile for selected user ID",
    }

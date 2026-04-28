from __future__ import annotations

from billing_mcp.tools import get_account_balance, get_workflow_authz


def test_billing_tool_declares_workflow_authz_metadata() -> None:
    metadata = get_workflow_authz(get_account_balance)

    assert metadata == {
        "scopes": ["read:billing", "read:accounts"],
        "scope_args": [],
        "op": "READ",
        "hitl": "Read billing balance for selected account ID",
    }

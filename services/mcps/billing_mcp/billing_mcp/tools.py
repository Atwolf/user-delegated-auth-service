from __future__ import annotations

from typing import Any

from mcp_runtime import FastMCP, get_workflow_authz, require_any_scope, restricted
from workflow_core import get_tool_authorization

__all__ = ["get_account_balance", "get_workflow_authz", "mcp", "restricted"]

mcp = FastMCP("billing-mcp")
_GET_ACCOUNT_BALANCE_AUTHZ = get_tool_authorization("get_account_balance")


@restricted(
    scopes=list(_GET_ACCOUNT_BALANCE_AUTHZ.auth0_scope_candidates),
    args=None,
    op=_GET_ACCOUNT_BALANCE_AUTHZ.op,
    hitl=_GET_ACCOUNT_BALANCE_AUTHZ.hitl_description,
)
@mcp.tool(
    name="get_account_balance",
    auth=require_any_scope(*_GET_ACCOUNT_BALANCE_AUTHZ.auth0_scope_candidates),
    tags={"billing", "read"},
)
async def get_account_balance(account_id: str) -> dict[str, Any]:
    return {"account_id": account_id, "balance_cents": 0, "currency": "USD"}

from __future__ import annotations

from typing import Any

from mcp_runtime import FastMCP, get_workflow_authz, require_scopes, restricted
from workflow_core import get_tool_authorization

__all__ = ["get_account_balance", "get_workflow_authz", "mcp", "restricted"]

mcp = FastMCP("billing-mcp")
_GET_ACCOUNT_BALANCE_AUTHZ = get_tool_authorization("get_account_balance")


@restricted(
    scopes=_GET_ACCOUNT_BALANCE_AUTHZ.scope_template,
    args=list(_GET_ACCOUNT_BALANCE_AUTHZ.scope_args),
    op=_GET_ACCOUNT_BALANCE_AUTHZ.op,
    hitl=_GET_ACCOUNT_BALANCE_AUTHZ.hitl_description,
)
@mcp.tool(
    name="get_account_balance",
    auth=require_scopes(*_GET_ACCOUNT_BALANCE_AUTHZ.runtime_scopes),
    tags={"billing", "read"},
)
async def get_account_balance(account_id: str) -> dict[str, Any]:
    return {"account_id": account_id, "balance_cents": 0, "currency": "USD"}

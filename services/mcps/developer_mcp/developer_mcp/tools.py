from __future__ import annotations

from typing import Any

from mcp_runtime import FastMCP, get_workflow_authz, require_any_scope, restricted
from workflow_core import get_tool_authorization

__all__ = ["get_developer_app", "get_workflow_authz", "mcp", "restricted"]

mcp = FastMCP("developer-mcp")
_GET_DEVELOPER_APP_AUTHZ = get_tool_authorization("get_developer_app")


@restricted(
    scopes=list(_GET_DEVELOPER_APP_AUTHZ.workflow_scope_templates),
    args=list(_GET_DEVELOPER_APP_AUTHZ.scope_args),
    op=_GET_DEVELOPER_APP_AUTHZ.op,
    hitl=_GET_DEVELOPER_APP_AUTHZ.hitl_description,
)
@mcp.tool(
    name="get_developer_app",
    auth=require_any_scope(*_GET_DEVELOPER_APP_AUTHZ.auth0_scope_candidates),
    tags={"developer", "read"},
)
async def get_developer_app(appid: str) -> dict[str, Any]:
    return {"appid": appid, "name": f"Developer app {appid}"}

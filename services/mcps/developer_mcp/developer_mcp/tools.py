from __future__ import annotations

from typing import Any

from mcp_runtime import FastMCP, get_workflow_authz, require_scopes, restricted
from workflow_core import get_tool_authorization

__all__ = ["get_developer_app", "get_workflow_authz", "mcp", "restricted"]

mcp = FastMCP("developer-mcp")
_GET_DEVELOPER_APP_AUTHZ = get_tool_authorization("get_developer_app")


@restricted(
    scopes=_GET_DEVELOPER_APP_AUTHZ.scope_template,
    args=list(_GET_DEVELOPER_APP_AUTHZ.scope_args),
    op=_GET_DEVELOPER_APP_AUTHZ.op,
    hitl=_GET_DEVELOPER_APP_AUTHZ.hitl_description,
)
@mcp.tool(
    name="get_developer_app",
    auth=require_scopes(*_GET_DEVELOPER_APP_AUTHZ.runtime_scopes),
    tags={"developer", "read"},
)
async def get_developer_app(appid: str) -> dict[str, Any]:
    return {"appid": appid, "name": f"Developer app {appid}"}

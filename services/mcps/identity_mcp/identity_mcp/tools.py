from __future__ import annotations

from typing import Any

from mcp_runtime import FastMCP, get_workflow_authz, require_scopes, restricted
from workflow_core import get_tool_authorization

__all__ = ["get_identity_profile", "get_workflow_authz", "mcp", "restricted"]

mcp = FastMCP("identity-mcp")
_GET_IDENTITY_PROFILE_AUTHZ = get_tool_authorization("get_identity_profile")


@restricted(
    scopes=_GET_IDENTITY_PROFILE_AUTHZ.scope_template,
    args=list(_GET_IDENTITY_PROFILE_AUTHZ.scope_args),
    op=_GET_IDENTITY_PROFILE_AUTHZ.op,
    hitl=_GET_IDENTITY_PROFILE_AUTHZ.hitl_description,
)
@mcp.tool(
    name="get_identity_profile",
    auth=require_scopes(*_GET_IDENTITY_PROFILE_AUTHZ.runtime_scopes),
    tags={"identity", "read"},
)
async def get_identity_profile(subject_user_id: str) -> dict[str, Any]:
    return {"subject_user_id": subject_user_id, "display_name": "Example User"}

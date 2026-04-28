from __future__ import annotations

from typing import Any

from mcp_runtime import FastMCP, get_workflow_authz, require_any_scope, restricted
from workflow_core import get_tool_authorization

__all__ = ["get_identity_profile", "get_workflow_authz", "mcp", "restricted"]

mcp = FastMCP("identity-mcp")
_GET_IDENTITY_PROFILE_AUTHZ = get_tool_authorization("get_identity_profile")


@restricted(
    scopes=list(_GET_IDENTITY_PROFILE_AUTHZ.auth0_scope_candidates),
    args=None,
    op=_GET_IDENTITY_PROFILE_AUTHZ.op,
    hitl=_GET_IDENTITY_PROFILE_AUTHZ.hitl_description,
)
@mcp.tool(
    name="get_identity_profile",
    auth=require_any_scope(*_GET_IDENTITY_PROFILE_AUTHZ.auth0_scope_candidates),
    tags={"identity", "read"},
)
async def get_identity_profile(subject_user_id: str) -> dict[str, Any]:
    return {"subject_user_id": subject_user_id, "display_name": "Example User"}

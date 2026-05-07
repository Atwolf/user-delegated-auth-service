from __future__ import annotations

from typing import Any

from mcp_runtime import FastMCP, get_workflow_authz, restricted
from workflow_core import get_tool_authorization

__all__ = [
    "get_workflow_authz",
    "inspect_vm",
    "mcp",
    "restricted",
    "restart_vm",
    "update_iam_binding",
]

mcp = FastMCP("cloud-mcp")
_INSPECT_VM_AUTHZ = get_tool_authorization("inspect_vm")
_RESTART_VM_AUTHZ = get_tool_authorization("restart_vm")
_UPDATE_IAM_AUTHZ = get_tool_authorization("update_iam_binding")


@restricted(
    scopes=list(_INSPECT_VM_AUTHZ.workflow_scope_templates),
    args=list(_INSPECT_VM_AUTHZ.scope_args),
    op=_INSPECT_VM_AUTHZ.op,
    hitl=_INSPECT_VM_AUTHZ.hitl_description,
)
@mcp.tool(
    name="inspect_vm",
    tags={"cloud", "vm", "read"},
)
async def inspect_vm(vm_id: str) -> dict[str, Any]:
    return {
        "vm_id": vm_id,
        "state": "running",
        "zone": "sample-zone-a",
    }


@restricted(
    scopes=list(_RESTART_VM_AUTHZ.workflow_scope_templates),
    args=list(_RESTART_VM_AUTHZ.scope_args),
    op=_RESTART_VM_AUTHZ.op,
    hitl=_RESTART_VM_AUTHZ.hitl_description,
)
@mcp.tool(
    name="restart_vm",
    tags={"cloud", "vm", "write"},
)
async def restart_vm(vm_id: str) -> dict[str, Any]:
    return {
        "vm_id": vm_id,
        "restart_state": "scheduled",
    }


@restricted(
    scopes=list(_UPDATE_IAM_AUTHZ.workflow_scope_templates),
    args=list(_UPDATE_IAM_AUTHZ.scope_args),
    op=_UPDATE_IAM_AUTHZ.op,
    hitl=_UPDATE_IAM_AUTHZ.hitl_description,
)
@mcp.tool(
    name="update_iam_binding",
    tags={"cloud", "iam", "admin"},
)
async def update_iam_binding(principal_id: str, role: str) -> dict[str, Any]:
    return {
        "principal_id": principal_id,
        "role": role,
        "binding_state": "pending_update",
    }

from __future__ import annotations

from typing import Any

from mcp_runtime import FastMCP, get_workflow_authz, restricted
from workflow_core import get_tool_authorization

__all__ = [
    "get_workflow_authz",
    "inspect_dns_record",
    "mcp",
    "restricted",
    "rotate_vpn_credential",
    "update_firewall_rule",
]

mcp = FastMCP("network-mcp")
_INSPECT_DNS_AUTHZ = get_tool_authorization("inspect_dns_record")
_UPDATE_FIREWALL_AUTHZ = get_tool_authorization("update_firewall_rule")
_ROTATE_VPN_AUTHZ = get_tool_authorization("rotate_vpn_credential")


@restricted(
    scopes=list(_INSPECT_DNS_AUTHZ.workflow_scope_templates),
    args=list(_INSPECT_DNS_AUTHZ.scope_args),
    op=_INSPECT_DNS_AUTHZ.op,
    hitl=_INSPECT_DNS_AUTHZ.hitl_description,
)
@mcp.tool(
    name="inspect_dns_record",
    tags={"network", "dns", "read"},
)
async def inspect_dns_record(record_name: str) -> dict[str, Any]:
    return {
        "record_name": record_name,
        "record_type": "A",
        "value": "192.0.2.10",
        "ttl": 300,
    }


@restricted(
    scopes=list(_UPDATE_FIREWALL_AUTHZ.workflow_scope_templates),
    args=list(_UPDATE_FIREWALL_AUTHZ.scope_args),
    op=_UPDATE_FIREWALL_AUTHZ.op,
    hitl=_UPDATE_FIREWALL_AUTHZ.hitl_description,
)
@mcp.tool(
    name="update_firewall_rule",
    tags={"network", "firewall", "write"},
)
async def update_firewall_rule(rule_id: str, cidr: str) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "cidr": cidr,
        "status": "pending_update",
    }


@restricted(
    scopes=list(_ROTATE_VPN_AUTHZ.workflow_scope_templates),
    args=list(_ROTATE_VPN_AUTHZ.scope_args),
    op=_ROTATE_VPN_AUTHZ.op,
    hitl=_ROTATE_VPN_AUTHZ.hitl_description,
)
@mcp.tool(
    name="rotate_vpn_credential",
    tags={"network", "vpn", "admin"},
)
async def rotate_vpn_credential(credential_id: str) -> dict[str, Any]:
    return {
        "credential_id": credential_id,
        "rotation_state": "scheduled",
    }

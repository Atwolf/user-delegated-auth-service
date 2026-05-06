from __future__ import annotations

from network_mcp.tools import (
    get_workflow_authz,
    inspect_dns_record,
    rotate_vpn_credential,
    update_firewall_rule,
)


def test_network_tool_workflow_authz_metadata() -> None:
    dns = get_workflow_authz(inspect_dns_record)
    firewall = get_workflow_authz(update_firewall_rule)
    vpn = get_workflow_authz(rotate_vpn_credential)

    assert dns["op"] == "READ"
    assert dns["hitl"] == "Inspect DNS record for selected hostname"
    assert firewall["op"] == "WRITE"
    assert firewall["hitl"] == "Update firewall rule for selected rule ID"
    assert vpn["op"] == "ADMIN"
    assert vpn["hitl"] == "Rotate VPN credential for selected credential ID"


async def test_network_tools_return_deterministic_placeholders() -> None:
    dns = await inspect_dns_record("app.example.com")
    firewall = await update_firewall_rule("fw-1", "203.0.113.0/24")
    vpn = await rotate_vpn_credential("vpn-1")

    assert dns["record_name"] == "app.example.com"
    assert firewall["status"] == "pending_update"
    assert vpn["rotation_state"] == "scheduled"

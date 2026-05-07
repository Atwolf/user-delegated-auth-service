from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from workflow_core import ToolIntent

from .models import PlanWorkflowRequest

ArgumentsFactory = Callable[[PlanWorkflowRequest], dict[str, object]]


@dataclass(frozen=True)
class IntentRule:
    keywords: frozenset[str]
    mcp_server: str
    tool_name: str
    reason: str
    arguments: ArgumentsFactory


class IntentOnlyAgent:
    name: str
    description: str
    rules: tuple[IntentRule, ...]

    def propose(self, request: PlanWorkflowRequest) -> list[ToolIntent]:
        normalized_query = request.query.casefold()
        proposals: list[ToolIntent] = []
        for rule in self.rules:
            if any(keyword in normalized_query for keyword in rule.keywords):
                proposals.append(
                    ToolIntent(
                        agent_name=self.name,
                        mcp_server=rule.mcp_server,
                        tool_name=rule.tool_name,
                        arguments=rule.arguments(request),
                        reason=rule.reason,
                        metadata_ref=f"tool_catalog:{rule.tool_name}",
                    )
                )
        return proposals


class NetworkServicesAgent(IntentOnlyAgent):
    name = "network_services_agent"
    description = "Proposes network MCP intents for network, VPN, DNS, and firewall questions."
    rules = (
        IntentRule(
            keywords=frozenset({"network", "subnet", "routing", "route"}),
            mcp_server="network-mcp",
            tool_name="inspect_dns_record",
            reason="Query references network service topology or routing.",
            arguments=lambda request: {"record_name": _dns_record(request)},
        ),
        IntentRule(
            keywords=frozenset({"vpn", "tunnel", "ipsec", "wireguard"}),
            mcp_server="network-mcp",
            tool_name="rotate_vpn_credential",
            reason="Query references VPN connectivity.",
            arguments=lambda request: {"credential_id": "vpn-sample"},
        ),
        IntentRule(
            keywords=frozenset({"dns", "domain", "record", "resolver"}),
            mcp_server="network-mcp",
            tool_name="inspect_dns_record",
            reason="Query references DNS configuration.",
            arguments=lambda request: {"record_name": _dns_record(request)},
        ),
        IntentRule(
            keywords=frozenset({"firewall", "security group", "acl", "ingress", "egress"}),
            mcp_server="network-mcp",
            tool_name="update_firewall_rule",
            reason="Query references firewall or packet-filtering policy.",
            arguments=lambda request: {"rule_id": "fw-sample", "cidr": "203.0.113.0/24"},
        ),
    )


class CloudOperationsAgent(IntentOnlyAgent):
    name = "cloud_operations_agent"
    description = "Proposes cloud MCP intents for VM, bucket, IAM, and cloud operations questions."
    rules = (
        IntentRule(
            keywords=frozenset({"vm", "instance", "compute", "server"}),
            mcp_server="cloud-mcp",
            tool_name="inspect_vm",
            reason="Query references compute or VM operations.",
            arguments=lambda request: {"vm_id": "vm-sample"},
        ),
        IntentRule(
            keywords=frozenset({"iam", "role", "policy", "permission", "principal"}),
            mcp_server="cloud-mcp",
            tool_name="update_iam_binding",
            reason="Query references identity and access management.",
            arguments=lambda request: {"principal_id": "user-sample", "role": "roles/viewer"},
        ),
        IntentRule(
            keywords=frozenset({"cloud", "project", "region", "quota"}),
            mcp_server="cloud-mcp",
            tool_name="inspect_vm",
            reason="Query references cloud operations posture.",
            arguments=lambda request: {"vm_id": "vm-sample"},
        ),
    )


def default_read_intent(request: PlanWorkflowRequest) -> ToolIntent:
    return ToolIntent(
        agent_name="coordinator_dispatcher",
        mcp_server="workflow-runtime",
        tool_name="inspect_request",
        arguments={
            "query": request.query,
        },
        reason="No specialist keyword matched; preserve a read-only planning boundary.",
        metadata_ref="tool_catalog:inspect_request",
    )


AGENTS: tuple[IntentOnlyAgent, ...] = (
    NetworkServicesAgent(),
    CloudOperationsAgent(),
)


def _dns_record(request: PlanWorkflowRequest) -> str:
    tokens = [token.strip(".,") for token in request.query.split()]
    return next((token for token in tokens if "." in token), "app.example.com")

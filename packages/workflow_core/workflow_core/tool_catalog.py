from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from workflow_core.models import ScopeRequirement


@dataclass(frozen=True)
class ToolAuthorizationSpec:
    tool_name: str
    auth0_scope_candidates: tuple[str, ...]
    workflow_scope_templates: tuple[str, ...]
    scope_args: tuple[str, ...]
    op: str
    hitl_description: str
    blast_radius: Literal["none", "low", "medium", "high"] = "low"
    downstream_audience: str | None = None

    @property
    def has_dynamic_workflow_scopes(self) -> bool:
        return bool(self.scope_args)

    def to_scope_requirements(self) -> list[ScopeRequirement]:
        return [
            ScopeRequirement(
                scope_template=scope_template,
                scope_args=list(self.scope_args),
                op=self.op,
                hitl_description=self.hitl_description,
            )
            for scope_template in self.workflow_scope_templates
        ]


TOOL_AUTHORIZATION_CATALOG: dict[str, ToolAuthorizationSpec] = {
    "get_identity_profile": ToolAuthorizationSpec(
        tool_name="get_identity_profile",
        auth0_scope_candidates=("read:identity", "read:users", "profile", "email"),
        workflow_scope_templates=("read:user:{subject_user_id}",),
        scope_args=("subject_user_id",),
        op="READ",
        hitl_description="Read identity profile for selected user ID",
    ),
    "get_developer_app": ToolAuthorizationSpec(
        tool_name="get_developer_app",
        auth0_scope_candidates=("read:developer_apps", "read:apps", "read:developer"),
        workflow_scope_templates=("read:client:{appid}",),
        scope_args=("appid",),
        op="READ",
        hitl_description="Read developer app metadata for selected app ID",
    ),
    "get_account_balance": ToolAuthorizationSpec(
        tool_name="get_account_balance",
        auth0_scope_candidates=("read:billing", "read:accounts"),
        workflow_scope_templates=("read:account:{account_id}",),
        scope_args=("account_id",),
        op="READ",
        hitl_description="Read billing balance for selected account ID",
    ),
    "propose_workflow_plan": ToolAuthorizationSpec(
        tool_name="propose_workflow_plan",
        auth0_scope_candidates=("plan:workflow", "read:workflow"),
        workflow_scope_templates=("plan:workflow",),
        scope_args=(),
        op="READ",
        hitl_description="Review the user request and propose workflow steps",
        blast_radius="none",
    ),
    "inspect_dns_record": ToolAuthorizationSpec(
        tool_name="inspect_dns_record",
        auth0_scope_candidates=("read:network", "read:dns"),
        workflow_scope_templates=("read:dns:{record_name}",),
        scope_args=("record_name",),
        op="READ",
        hitl_description="Inspect DNS record for selected hostname",
        blast_radius="low",
        downstream_audience="network-mcp",
    ),
    "update_firewall_rule": ToolAuthorizationSpec(
        tool_name="update_firewall_rule",
        auth0_scope_candidates=("write:network", "write:firewall"),
        workflow_scope_templates=("write:firewall:{rule_id}",),
        scope_args=("rule_id",),
        op="WRITE",
        hitl_description="Update firewall rule for selected rule ID",
        blast_radius="high",
        downstream_audience="network-mcp",
    ),
    "rotate_vpn_credential": ToolAuthorizationSpec(
        tool_name="rotate_vpn_credential",
        auth0_scope_candidates=("admin:network", "admin:vpn"),
        workflow_scope_templates=("admin:vpn:{credential_id}",),
        scope_args=("credential_id",),
        op="ADMIN",
        hitl_description="Rotate VPN credential for selected credential ID",
        blast_radius="high",
        downstream_audience="network-mcp",
    ),
    "inspect_vm": ToolAuthorizationSpec(
        tool_name="inspect_vm",
        auth0_scope_candidates=("read:cloud", "read:vm"),
        workflow_scope_templates=("read:vm:{vm_id}",),
        scope_args=("vm_id",),
        op="READ",
        hitl_description="Inspect virtual machine state for selected VM",
        blast_radius="low",
        downstream_audience="cloud-mcp",
    ),
    "restart_vm": ToolAuthorizationSpec(
        tool_name="restart_vm",
        auth0_scope_candidates=("write:cloud", "write:vm"),
        workflow_scope_templates=("write:vm:{vm_id}",),
        scope_args=("vm_id",),
        op="WRITE",
        hitl_description="Restart selected virtual machine",
        blast_radius="medium",
        downstream_audience="cloud-mcp",
    ),
    "update_iam_binding": ToolAuthorizationSpec(
        tool_name="update_iam_binding",
        auth0_scope_candidates=("admin:cloud", "admin:iam"),
        workflow_scope_templates=("admin:iam:{principal_id}",),
        scope_args=("principal_id",),
        op="ADMIN",
        hitl_description="Update IAM binding for selected principal",
        blast_radius="high",
        downstream_audience="cloud-mcp",
    ),
}

def get_tool_authorization(tool_name: str) -> ToolAuthorizationSpec:
    return TOOL_AUTHORIZATION_CATALOG[tool_name]


def scope_requirements_for_tool(tool_name: str) -> list[ScopeRequirement]:
    return get_tool_authorization(tool_name).to_scope_requirements()


def scope_requirements_for_auth0_token(
    tool_name: str,
    issued_scopes: Iterable[str],
) -> list[ScopeRequirement]:
    selected_scopes = select_auth0_scopes_for_tool(tool_name, issued_scopes)
    spec = get_tool_authorization(tool_name)
    preferred_scopes = set(spec.auth0_scope_candidates).intersection(selected_scopes)
    if preferred_scopes and spec.has_dynamic_workflow_scopes:
        return spec.to_scope_requirements()

    return [
        ScopeRequirement(
            scope_template=scope,
            scope_args=[],
            op=spec.op,
            hitl_description=spec.hitl_description,
        )
        for scope in selected_scopes
    ]


def select_auth0_scopes_for_tool(
    tool_name: str,
    issued_scopes: Iterable[str],
) -> list[str]:
    normalized_issued_scopes = sorted({scope.strip() for scope in issued_scopes if scope.strip()})
    if not normalized_issued_scopes:
        return []

    spec = get_tool_authorization(tool_name)
    preferred = [
        scope for scope in spec.auth0_scope_candidates if scope in normalized_issued_scopes
    ]
    if preferred:
        return sorted(preferred)

    # Tenants can name API permissions differently. When Auth0 has already issued
    # scopes for this client, keep the workflow manifest aligned with that token
    # instead of inventing DOE-style scopes that the token can never satisfy.
    return normalized_issued_scopes

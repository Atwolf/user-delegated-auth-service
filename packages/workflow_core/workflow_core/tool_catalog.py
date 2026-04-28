from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from workflow_core.models import ScopeRequirement


@dataclass(frozen=True)
class ToolAuthorizationSpec:
    tool_name: str
    auth0_scope_candidates: tuple[str, ...]
    op: str
    hitl_description: str

    def to_scope_requirement(self) -> ScopeRequirement:
        return ScopeRequirement(
            scope_template=self.auth0_scope_candidates[0],
            scope_args=[],
            op=self.op,
            hitl_description=self.hitl_description,
        )


TOOL_AUTHORIZATION_CATALOG: dict[str, ToolAuthorizationSpec] = {
    "get_identity_profile": ToolAuthorizationSpec(
        tool_name="get_identity_profile",
        auth0_scope_candidates=("read:identity", "read:users", "profile", "email"),
        op="READ",
        hitl_description="Read identity profile for selected user ID",
    ),
    "get_developer_app": ToolAuthorizationSpec(
        tool_name="get_developer_app",
        auth0_scope_candidates=("read:developer_apps", "read:apps", "read:developer"),
        op="READ",
        hitl_description="Read developer app metadata for selected app ID",
    ),
    "get_account_balance": ToolAuthorizationSpec(
        tool_name="get_account_balance",
        auth0_scope_candidates=("read:billing", "read:accounts"),
        op="READ",
        hitl_description="Read billing balance for selected account ID",
    ),
    "propose_workflow_plan": ToolAuthorizationSpec(
        tool_name="propose_workflow_plan",
        auth0_scope_candidates=("plan:workflow", "read:workflow"),
        op="READ",
        hitl_description="Review the user request and propose workflow steps",
    ),
}

INSPECT_REQUEST_AUTHORIZATION = ToolAuthorizationSpec(
    tool_name="inspect_request",
    auth0_scope_candidates=("read:workflow",),
    op="READ",
    hitl_description="Inspect the user request for workflow planning",
)


def get_tool_authorization(tool_name: str) -> ToolAuthorizationSpec:
    return TOOL_AUTHORIZATION_CATALOG.get(tool_name, INSPECT_REQUEST_AUTHORIZATION)


def scope_requirements_for_tool(tool_name: str) -> list[ScopeRequirement]:
    return [get_tool_authorization(tool_name).to_scope_requirement()]


def scope_requirements_for_auth0_token(
    tool_name: str,
    issued_scopes: Iterable[str],
) -> list[ScopeRequirement]:
    selected_scopes = select_auth0_scopes_for_tool(tool_name, issued_scopes)
    return [
        ScopeRequirement(
            scope_template=scope,
            scope_args=[],
            op=get_tool_authorization(tool_name).op,
            hitl_description=get_tool_authorization(tool_name).hitl_description,
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

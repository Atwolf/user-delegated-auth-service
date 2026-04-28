from __future__ import annotations

from dataclasses import dataclass

from workflow_core.models import ScopeRequirement


@dataclass(frozen=True)
class ToolAuthorizationSpec:
    tool_name: str
    scope_template: str
    scope_args: tuple[str, ...]
    op: str
    hitl_description: str
    runtime_scopes: tuple[str, ...] = ()

    def to_scope_requirement(self) -> ScopeRequirement:
        return ScopeRequirement(
            scope_template=self.scope_template,
            scope_args=list(self.scope_args),
            op=self.op,
            hitl_description=self.hitl_description,
        )


TOOL_AUTHORIZATION_CATALOG: dict[str, ToolAuthorizationSpec] = {
    "get_identity_profile": ToolAuthorizationSpec(
        tool_name="get_identity_profile",
        scope_template="DOE.Identity.{subject_user_id}",
        scope_args=("subject_user_id",),
        op="READ",
        hitl_description="Read identity profile for selected user ID",
        runtime_scopes=("DOE.Identity.read",),
    ),
    "get_developer_app": ToolAuthorizationSpec(
        tool_name="get_developer_app",
        scope_template="DOE.Developer.{appid}",
        scope_args=("appid",),
        op="READ",
        hitl_description="Read developer app metadata for selected app ID",
        runtime_scopes=("DOE.Developer.read",),
    ),
    "get_account_balance": ToolAuthorizationSpec(
        tool_name="get_account_balance",
        scope_template="DOE.Billing.{account_id}",
        scope_args=("account_id",),
        op="READ",
        hitl_description="Read billing balance for selected account ID",
        runtime_scopes=("DOE.Billing.read",),
    ),
    "propose_workflow_plan": ToolAuthorizationSpec(
        tool_name="propose_workflow_plan",
        scope_template="DOE.Workflow.plan",
        scope_args=(),
        op="READ",
        hitl_description="Review the user request and propose workflow steps",
    ),
}

INSPECT_REQUEST_AUTHORIZATION = ToolAuthorizationSpec(
    tool_name="inspect_request",
    scope_template="DOE.Workflow.inspect",
    scope_args=(),
    op="READ",
    hitl_description="Inspect the user request for workflow planning",
)


def get_tool_authorization(tool_name: str) -> ToolAuthorizationSpec:
    return TOOL_AUTHORIZATION_CATALOG.get(tool_name, INSPECT_REQUEST_AUTHORIZATION)


def scope_requirements_for_tool(tool_name: str) -> list[ScopeRequirement]:
    return [get_tool_authorization(tool_name).to_scope_requirement()]

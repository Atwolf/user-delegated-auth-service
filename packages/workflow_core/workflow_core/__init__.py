from __future__ import annotations

from workflow_core.authz import (
    ScopeMaterializationError,
    WorkflowAuthzMetadata,
    get_workflow_authz_metadata,
    materialize_scope,
    materialize_scopes,
    materialize_scopes_for_proposal,
    restricted,
    scope_requirements_from_callable,
)
from workflow_core.grants import (
    ExecutionGrantError,
    sign_execution_grant,
    verify_execution_grant,
)
from workflow_core.hashing import canonical_json, plan_hash
from workflow_core.models import (
    ApprovedWorkflow,
    AuthorizationBundle,
    EgressRequest,
    ExecutionGrant,
    ScopeRequirement,
    ToolIntent,
    ToolProposal,
    WorkflowPlan,
    WorkflowPolicyDecision,
    WorkflowStatus,
    WorkflowStep,
)
from workflow_core.policy import evaluate_workflow_policy
from workflow_core.tool_catalog import (
    TOOL_AUTHORIZATION_CATALOG,
    ToolAuthorizationSpec,
    get_tool_authorization,
    scope_requirements_for_auth0_token,
    scope_requirements_for_tool,
    select_auth0_scopes_for_tool,
)

__all__ = [
    "ApprovedWorkflow",
    "AuthorizationBundle",
    "EgressRequest",
    "ExecutionGrant",
    "ExecutionGrantError",
    "ScopeMaterializationError",
    "ScopeRequirement",
    "TOOL_AUTHORIZATION_CATALOG",
    "ToolAuthorizationSpec",
    "ToolIntent",
    "ToolProposal",
    "WorkflowAuthzMetadata",
    "WorkflowPolicyDecision",
    "WorkflowPlan",
    "WorkflowStatus",
    "WorkflowStep",
    "canonical_json",
    "evaluate_workflow_policy",
    "get_tool_authorization",
    "get_workflow_authz_metadata",
    "materialize_scope",
    "materialize_scopes",
    "materialize_scopes_for_proposal",
    "plan_hash",
    "restricted",
    "scope_requirements_for_auth0_token",
    "scope_requirements_for_tool",
    "select_auth0_scopes_for_tool",
    "sign_execution_grant",
    "scope_requirements_from_callable",
    "verify_execution_grant",
]

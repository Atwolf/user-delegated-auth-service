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
from workflow_core.hashing import canonical_json, plan_hash
from workflow_core.models import (
    ApprovedWorkflow,
    AuthorizationBundle,
    ScopeRequirement,
    ToolProposal,
    WorkflowPlan,
    WorkflowStatus,
    WorkflowStep,
)
from workflow_core.tool_catalog import (
    INSPECT_REQUEST_AUTHORIZATION,
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
    "INSPECT_REQUEST_AUTHORIZATION",
    "ScopeMaterializationError",
    "ScopeRequirement",
    "TOOL_AUTHORIZATION_CATALOG",
    "ToolAuthorizationSpec",
    "ToolProposal",
    "WorkflowAuthzMetadata",
    "WorkflowPlan",
    "WorkflowStatus",
    "WorkflowStep",
    "canonical_json",
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
    "scope_requirements_from_callable",
]

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import fastmcp.server.auth as fastmcp_auth
from fastmcp import FastMCP
from workflow_core import WorkflowAuthzMetadata, get_workflow_authz_metadata, restricted

require_scopes: Any = fastmcp_auth.require_scopes


def require_any_scope(*scopes: str) -> Callable[[Any], bool]:
    required = {scope for scope in scopes if scope}
    if not required:
        raise ValueError("at least one scope is required")

    def check(ctx: Any) -> bool:
        token = getattr(ctx, "token", None)
        token_scopes = getattr(token, "scopes", None)
        if token_scopes is None:
            return False
        return bool(required.intersection(set(token_scopes)))

    return check


def get_workflow_authz(tool: Callable[..., Any]) -> WorkflowAuthzMetadata:
    metadata = get_workflow_authz_metadata(tool)
    if metadata is None:
        raise LookupError("tool is missing workflow authorization metadata")
    return metadata


__all__ = [
    "FastMCP",
    "WorkflowAuthzMetadata",
    "get_workflow_authz",
    "require_any_scope",
    "require_scopes",
    "restricted",
]

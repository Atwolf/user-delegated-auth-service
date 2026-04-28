from __future__ import annotations

from collections.abc import Callable
from typing import Any

import fastmcp.server.auth as fastmcp_auth
from fastmcp import FastMCP
from workflow_core import WorkflowAuthzMetadata, get_workflow_authz_metadata, restricted

require_scopes: Any = fastmcp_auth.require_scopes


def get_workflow_authz(tool: Callable[..., Any]) -> WorkflowAuthzMetadata:
    metadata = get_workflow_authz_metadata(tool)
    if metadata is None:
        raise LookupError("tool is missing workflow authorization metadata")
    return metadata


__all__ = [
    "FastMCP",
    "WorkflowAuthzMetadata",
    "get_workflow_authz",
    "require_scopes",
    "restricted",
]

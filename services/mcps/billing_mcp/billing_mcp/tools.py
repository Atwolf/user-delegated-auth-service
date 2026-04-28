from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar, cast

_require_scopes_impl: Any
_fastmcp_class: Any

try:  # pragma: no cover - exercised when FastMCP is installed.
    import fastmcp.server.auth as fastmcp_auth
    from fastmcp import FastMCP as _InstalledFastMCP
except ImportError:  # pragma: no cover - keeps contract tests runnable without FastMCP.

    class _FallbackFastMCP:
        def __init__(self, name: str) -> None:
            self.name = name
            self.tools: dict[str, Callable[..., Any]] = {}

        def tool(
            self,
            fn: Callable[..., Any] | None = None,
            **metadata: Any,
        ) -> Callable[..., Any]:
            def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                setattr(func, "__fastmcp_tool__", metadata)  # noqa: B010
                self.tools[metadata.get("name", func.__name__)] = func
                return func

            if fn is not None:
                return _decorator(fn)
            return _decorator

    def _fallback_require_scopes(*scopes: str) -> tuple[str, ...]:
        return scopes

    _require_scopes_impl = _fallback_require_scopes
    _fastmcp_class = _FallbackFastMCP
else:  # pragma: no cover - exercised when FastMCP is installed.
    _require_scopes_impl = fastmcp_auth.require_scopes
    _fastmcp_class = _InstalledFastMCP

fastmcp_require_scopes: Any = _require_scopes_impl
FastMCP: Any = _fastmcp_class


P = ParamSpec("P")
R = TypeVar("R")

WorkflowAuthzMetadata = dict[str, str | list[str]]


def restricted(
    *,
    scopes: str | list[str],
    args: str | list[str] | None,
    op: str,
    hitl: str,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Attach declarative auth metadata used by plan-authorize-execute."""

    declared_scopes = [scopes] if isinstance(scopes, str) else scopes
    declared_args = [args] if isinstance(args, str) else (args or [])

    def _decorator(fn: Callable[P, R]) -> Callable[P, R]:
        setattr(  # noqa: B010
            fn,
            "__workflow_authz__",
            {
                "scopes": declared_scopes,
                "scope_args": declared_args,
                "op": op,
                "hitl": hitl,
            },
        )
        return fn

    return _decorator


def get_workflow_authz(tool: object) -> WorkflowAuthzMetadata:
    metadata = getattr(tool, "__workflow_authz__", None)
    if not isinstance(metadata, dict):
        raise LookupError("tool is missing workflow authorization metadata")
    return cast(WorkflowAuthzMetadata, metadata)


mcp = FastMCP("billing-mcp")


@restricted(
    scopes="DOE.Billing.{account_id}",
    args="account_id",
    op="READ",
    hitl="Read billing balance for selected account ID",
)
@mcp.tool(
    name="get_account_balance",
    auth=fastmcp_require_scopes("DOE.Billing.read"),
    tags={"billing", "read"},
)
async def get_account_balance(account_id: str) -> dict[str, Any]:
    return {"account_id": account_id, "balance_cents": 0, "currency": "USD"}

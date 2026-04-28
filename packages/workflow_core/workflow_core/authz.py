from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, ParamSpec, TypeAlias, TypeVar, cast

from workflow_core.models import ScopeRequirement, ToolProposal

P = ParamSpec("P")
R = TypeVar("R")

WORKFLOW_AUTHZ_ATTR = "__workflow_authz__"
_TEMPLATE_FIELD_RE = re.compile(r"{([A-Za-z_][A-Za-z0-9_]*)}")

ScalarScopeValue: TypeAlias = str | int | float | bool
WorkflowAuthzMetadata: TypeAlias = dict[str, list[str] | str]


class ScopeMaterializationError(ValueError):
    """Raised when a scope template cannot be rendered from tool arguments."""


def restricted(
    *,
    scopes: str | Sequence[str],
    args: str | Sequence[str] | None,
    op: str,
    hitl: str,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    declared_scopes = _coerce_non_empty_list(scopes, field_name="scopes")
    declared_args = _coerce_non_empty_list(args, field_name="args") if args else []

    metadata: WorkflowAuthzMetadata = {
        "scopes": declared_scopes,
        "scope_args": declared_args,
        "op": _require_non_empty(op, field_name="op"),
        "hitl": _require_non_empty(hitl, field_name="hitl"),
    }

    def _decorator(fn: Callable[P, R]) -> Callable[P, R]:
        setattr(fn, WORKFLOW_AUTHZ_ATTR, metadata)
        return fn

    return _decorator


def get_workflow_authz_metadata(fn: Callable[..., Any]) -> WorkflowAuthzMetadata | None:
    metadata = getattr(fn, WORKFLOW_AUTHZ_ATTR, None)
    if metadata is None:
        return None
    if not isinstance(metadata, dict):
        raise TypeError(f"{WORKFLOW_AUTHZ_ATTR} must be a dictionary")
    return {
        "scopes": list(cast(list[str], metadata["scopes"])),
        "scope_args": list(cast(list[str], metadata["scope_args"])),
        "op": cast(str, metadata["op"]),
        "hitl": cast(str, metadata["hitl"]),
    }


def scope_requirements_from_callable(fn: Callable[..., Any]) -> list[ScopeRequirement]:
    metadata = get_workflow_authz_metadata(fn)
    if metadata is None:
        return []

    scopes = cast(list[str], metadata["scopes"])
    scope_args = cast(list[str], metadata["scope_args"])
    op = cast(str, metadata["op"])
    hitl = cast(str, metadata["hitl"])
    return [
        ScopeRequirement(
            scope_template=scope,
            scope_args=scope_args,
            op=op,
            hitl_description=hitl,
        )
        for scope in scopes
    ]


def materialize_scope(
    requirement: ScopeRequirement,
    tool_arguments: Mapping[str, object],
) -> str:
    required_arg_names = set(requirement.scope_args)
    required_arg_names.update(_template_arg_names(requirement.scope_template))
    missing_args = sorted(name for name in required_arg_names if name not in tool_arguments)
    if missing_args:
        missing = ", ".join(missing_args)
        raise ScopeMaterializationError(f"missing required scope argument(s): {missing}")

    def _replace(match: re.Match[str]) -> str:
        arg_name = match.group(1)
        return _render_scope_value(arg_name, tool_arguments[arg_name])

    rendered_scope = _TEMPLATE_FIELD_RE.sub(_replace, requirement.scope_template)
    if "{" in rendered_scope or "}" in rendered_scope:
        raise ScopeMaterializationError("unsupported scope template syntax")
    return rendered_scope


def materialize_scopes(
    requirements: Iterable[ScopeRequirement],
    tool_arguments: Mapping[str, object],
) -> list[str]:
    return sorted(
        {
            materialize_scope(requirement, tool_arguments)
            for requirement in requirements
        }
    )


def materialize_scopes_for_proposal(
    proposal: ToolProposal,
    requirements: Iterable[ScopeRequirement],
) -> list[str]:
    return materialize_scopes(requirements, proposal.arguments)


def _template_arg_names(scope_template: str) -> set[str]:
    return set(_TEMPLATE_FIELD_RE.findall(scope_template))


def _render_scope_value(arg_name: str, value: object) -> str:
    if value is None:
        raise ScopeMaterializationError(f"scope argument {arg_name!r} cannot be null")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    raise ScopeMaterializationError(
        f"scope argument {arg_name!r} must be a string, integer, float, or boolean"
    )


def _coerce_non_empty_list(
    value: str | Sequence[str] | None,
    *,
    field_name: str,
) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_require_non_empty(value, field_name=field_name)]
    values = [_require_non_empty(item, field_name=field_name) for item in value]
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    return values


def _require_non_empty(value: str, *, field_name: str) -> str:
    if not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value

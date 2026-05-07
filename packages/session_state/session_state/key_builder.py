from __future__ import annotations

from urllib.parse import quote

DEFAULT_KEY_PREFIX = "session_state:v1"
GLOBAL_TENANT_ID = "_"


def _encode_part(value: str, *, field_name: str) -> str:
    if value == "":
        raise ValueError(f"{field_name} must not be empty")
    return quote(value, safe="")


def _encode_tenant(tenant_id: str | None) -> str:
    if tenant_id is None:
        return GLOBAL_TENANT_ID
    return _encode_part(tenant_id, field_name="tenant_id")


def _validate_prefix(prefix: str) -> str:
    if prefix == "":
        raise ValueError("prefix must not be empty")
    return prefix


def build_session_key(
    *,
    user_id: str,
    session_id: str,
    tenant_id: str | None = None,
    prefix: str = DEFAULT_KEY_PREFIX,
) -> str:
    """Return the deterministic Redis key for a session state blob."""

    return (
        f"{_validate_prefix(prefix)}"
        f":tenant:{_encode_tenant(tenant_id)}"
        f":user:{_encode_part(user_id, field_name='user_id')}"
        f":session:{_encode_part(session_id, field_name='session_id')}"
    )


def build_workflow_key(
    *,
    user_id: str,
    session_id: str,
    workflow_id: str,
    tenant_id: str | None = None,
    prefix: str = DEFAULT_KEY_PREFIX,
) -> str:
    """Return the deterministic Redis key for a workflow state blob."""

    session_key = build_session_key(
        user_id=user_id,
        session_id=session_id,
        tenant_id=tenant_id,
        prefix=prefix,
    )
    return f"{session_key}:workflow:{_encode_part(workflow_id, field_name='workflow_id')}"


def build_session_events_key(
    *,
    user_id: str,
    session_id: str,
    tenant_id: str | None = None,
    prefix: str = DEFAULT_KEY_PREFIX,
) -> str:
    """Return the deterministic Redis list key for session-scoped events."""

    session_key = build_session_key(
        user_id=user_id,
        session_id=session_id,
        tenant_id=tenant_id,
        prefix=prefix,
    )
    return f"{session_key}:events"


def build_workflow_events_key(
    *,
    user_id: str,
    session_id: str,
    workflow_id: str,
    tenant_id: str | None = None,
    prefix: str = DEFAULT_KEY_PREFIX,
) -> str:
    """Return the deterministic Redis list key for workflow-scoped events."""

    workflow_key = build_workflow_key(
        user_id=user_id,
        session_id=session_id,
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        prefix=prefix,
    )
    return f"{workflow_key}:events"

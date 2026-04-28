from __future__ import annotations

import pytest
from session_state.key_builder import (
    build_session_events_key,
    build_session_key,
    build_workflow_events_key,
    build_workflow_key,
)


def test_session_key_is_deterministic_and_escapes_identity_parts() -> None:
    first = build_session_key(
        tenant_id=None,
        user_id="user:123",
        session_id="session/abc",
    )
    second = build_session_key(
        tenant_id=None,
        user_id="user:123",
        session_id="session/abc",
    )

    assert first == second
    assert first == "session_state:v1:tenant:_:user:user%3A123:session:session%2Fabc"


def test_session_key_includes_tenant_namespace() -> None:
    assert (
        build_session_key(
            tenant_id="tenant a",
            user_id="user-1",
            session_id="session-1",
        )
        == "session_state:v1:tenant:tenant%20a:user:user-1:session:session-1"
    )


def test_workflow_key_extends_session_key() -> None:
    assert (
        build_workflow_key(
            tenant_id="tenant",
            user_id="user",
            session_id="session",
            workflow_id="workflow:001",
        )
        == "session_state:v1:tenant:tenant:user:user:session:session:workflow:workflow%3A001"
    )


def test_event_keys_are_scoped_to_session_or_workflow() -> None:
    assert (
        build_session_events_key(
            tenant_id=None,
            user_id="user",
            session_id="session",
        )
        == "session_state:v1:tenant:_:user:user:session:session:events"
    )
    assert (
        build_workflow_events_key(
            tenant_id=None,
            user_id="user",
            session_id="session",
            workflow_id="workflow",
        )
        == "session_state:v1:tenant:_:user:user:session:session:workflow:workflow:events"
    )


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("user_id", {"user_id": "", "session_id": "session"}),
        ("session_id", {"user_id": "user", "session_id": ""}),
    ],
)
def test_key_builder_rejects_empty_required_parts(
    field_name: str,
    kwargs: dict[str, str],
) -> None:
    with pytest.raises(ValueError, match=field_name):
        build_session_key(**kwargs)

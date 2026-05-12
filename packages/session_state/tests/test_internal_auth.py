from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from session_state import (
    SESSION_CONTEXT_HEADER,
    SESSION_CONTEXT_SIGNATURE_HEADER,
    InternalAuthError,
    TrustedSessionContext,
    signed_session_context_headers,
    verify_session_context,
)


def _context(*, expires_at: datetime | None = None) -> TrustedSessionContext:
    return TrustedSessionContext(
        allowed_tools=["restart_vm"],
        correlation_id="corr-1",
        expires_at=expires_at or datetime.now(UTC) + timedelta(minutes=5),
        session_id="session-1",
        tenant_id="tenant-1",
        token_ref="auth0:sample",
        token_scopes=["write:vm"],
        user_id="user-1",
    )


def test_signed_session_context_round_trips() -> None:
    headers = signed_session_context_headers(_context(), secret="test-secret")

    verified = verify_session_context(
        encoded_context=headers[SESSION_CONTEXT_HEADER],
        signature=headers[SESSION_CONTEXT_SIGNATURE_HEADER],
        secret="test-secret",
    )

    assert verified.user_id == "user-1"
    assert verified.session_id == "session-1"
    assert verified.tenant_id == "tenant-1"
    assert verified.allowed_tools == ["restart_vm"]


def test_signed_session_context_rejects_tampering() -> None:
    headers = signed_session_context_headers(_context(), secret="test-secret")
    tampered = headers[SESSION_CONTEXT_HEADER][:-2] + "AA"

    with pytest.raises(InternalAuthError, match="invalid session context signature"):
        verify_session_context(
            encoded_context=tampered,
            signature=headers[SESSION_CONTEXT_SIGNATURE_HEADER],
            secret="test-secret",
        )


def test_signed_session_context_rejects_expired_context() -> None:
    headers = signed_session_context_headers(
        _context(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
        secret="test-secret",
    )

    with pytest.raises(InternalAuthError, match="signed session context has expired"):
        verify_session_context(
            encoded_context=headers[SESSION_CONTEXT_HEADER],
            signature=headers[SESSION_CONTEXT_SIGNATURE_HEADER],
            secret="test-secret",
        )

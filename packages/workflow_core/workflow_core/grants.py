from __future__ import annotations

import hmac
from hashlib import sha256

from workflow_core.hashing import canonical_json
from workflow_core.models import ExecutionGrant


class ExecutionGrantError(ValueError):
    """Raised when an execution grant cannot be trusted."""


def sign_execution_grant(grant: ExecutionGrant, *, secret: str) -> str:
    if not secret:
        raise ExecutionGrantError("execution grant secret is required")
    return hmac.new(
        secret.encode("utf-8"),
        canonical_json(grant).encode("utf-8"),
        sha256,
    ).hexdigest()


def verify_execution_grant(
    grant: ExecutionGrant,
    *,
    signature: str | None,
    secret: str,
) -> None:
    if not signature:
        raise ExecutionGrantError("execution grant signature is required")
    expected = sign_execution_grant(grant, secret=secret)
    if not hmac.compare_digest(signature, expected):
        raise ExecutionGrantError("invalid execution grant signature")

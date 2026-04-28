from __future__ import annotations

from types import SimpleNamespace

import pytest
from mcp_runtime import get_workflow_authz, require_any_scope, restricted


def test_restricted_attaches_workflow_metadata() -> None:
    @restricted(
        scopes="DOE.Sample.{appid}",
        args="appid",
        op="READ",
        hitl="Read sample app",
    )
    def tool() -> None:
        return None

    assert get_workflow_authz(tool) == {
        "scopes": ["DOE.Sample.{appid}"],
        "scope_args": ["appid"],
        "op": "READ",
        "hitl": "Read sample app",
    }


def test_get_workflow_authz_rejects_missing_metadata() -> None:
    with pytest.raises(LookupError):
        get_workflow_authz(object())


def test_require_any_scope_accepts_one_matching_auth0_scope() -> None:
    check = require_any_scope("read:users", "profile")

    assert check(SimpleNamespace(token=SimpleNamespace(scopes=["profile"])))
    assert not check(SimpleNamespace(token=SimpleNamespace(scopes=["read:apps"])))
    assert not check(SimpleNamespace(token=None))

from __future__ import annotations

import pytest
from mcp_runtime import get_workflow_authz, restricted


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

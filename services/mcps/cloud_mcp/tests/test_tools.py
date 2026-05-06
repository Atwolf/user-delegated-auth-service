from __future__ import annotations

from cloud_mcp.tools import (
    get_workflow_authz,
    inspect_vm,
    restart_vm,
    update_iam_binding,
)


def test_cloud_tool_workflow_authz_metadata() -> None:
    inspect = get_workflow_authz(inspect_vm)
    restart = get_workflow_authz(restart_vm)
    iam = get_workflow_authz(update_iam_binding)

    assert inspect["op"] == "READ"
    assert inspect["hitl"] == "Inspect virtual machine state for selected VM"
    assert restart["op"] == "WRITE"
    assert restart["hitl"] == "Restart selected virtual machine"
    assert iam["op"] == "ADMIN"
    assert iam["hitl"] == "Update IAM binding for selected principal"


async def test_cloud_tools_return_deterministic_placeholders() -> None:
    vm = await inspect_vm("vm-1")
    restart = await restart_vm("vm-1")
    iam = await update_iam_binding("user-1", "roles/viewer")

    assert vm["state"] == "running"
    assert restart["restart_state"] == "scheduled"
    assert iam["binding_state"] == "pending_update"

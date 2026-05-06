from __future__ import annotations

from agent_service.app import create_app
from fastapi.testclient import TestClient


def test_agent_listing_includes_worker_c_subagents() -> None:
    client = TestClient(create_app())

    response = client.get("/agents")

    assert response.status_code == 200
    names = [agent["name"] for agent in response.json()["agents"]]
    assert names == ["network_services_agent", "cloud_operations_agent"]


def test_plan_workflow_returns_network_intent() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/workflows/plan",
        json={
            "query": "Check VPN and DNS health for the branch network",
            "user_id": "user-1",
            "session_id": "session-1",
            "token_ref": "auth0:sample",
            "token_scopes": ["read:workflow"],
        },
    )

    assert response.status_code == 200
    workflow = response.json()["workflow"]
    tool_names = [intent["tool_name"] for intent in workflow["tool_intents"]]
    assert "rotate_vpn_credential" in tool_names
    assert "inspect_dns_record" in tool_names
    assert workflow["status"] == "awaiting_approval"
    assert workflow["policy"]["requires_hitl"] is True
    assert workflow["proposal"]["steps"][0]["operation_type"] == "READ"


def test_plan_workflow_returns_cloud_intent() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/workflows/plan",
        json={
            "query": "Review VM and IAM posture in the cloud project",
            "user_id": "user-1",
            "session_id": "session-1",
            "allowed_tools": ["inspect_vm", "update_iam_binding"],
        },
    )

    assert response.status_code == 200
    workflow = response.json()["workflow"]
    tool_names = [intent["tool_name"] for intent in workflow["tool_intents"]]
    assert "inspect_vm" in tool_names
    assert "update_iam_binding" in tool_names
    assert workflow["policy"]["blast_radius"] == "high"


def test_plan_workflow_defaults_to_read_only_noop_intent() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/workflows/plan",
        json={
            "query": "What can you help me understand today?",
            "user_id": "user-1",
            "session_id": "session-1",
        },
    )

    assert response.status_code == 200
    workflow = response.json()["workflow"]
    assert workflow["tool_intents"] == [
        {
            "agent_name": "coordinator_dispatcher",
            "mcp_server": "workflow-runtime",
            "tool_name": "inspect_request",
            "arguments": {
                "query": "What can you help me understand today?",
            },
            "reason": "No specialist keyword matched; preserve a read-only planning boundary.",
            "metadata_ref": "tool_catalog:inspect_request",
        }
    ]
    assert workflow["status"] == "ready"
    assert workflow["proposal"]["steps"][0]["action"] == "inspect_request"

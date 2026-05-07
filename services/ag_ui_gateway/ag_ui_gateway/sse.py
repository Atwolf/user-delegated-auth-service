from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

from ag_ui_gateway.client import AgentServiceClient
from ag_ui_gateway.models import RunAgentInput


def encode_sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"), sort_keys=True)
    return f"event: {event}\ndata: {payload}\n\n"


async def stream_agent_events(
    request: RunAgentInput,
    agent_service: AgentServiceClient,
) -> AsyncIterator[str]:
    yield encode_sse(
        "RUN_STARTED",
        {
            "type": "RUN_STARTED",
            "threadId": request.thread_id,
            "runId": request.run_id,
        },
    )

    response_payload = await agent_service.plan_workflow(_workflow_plan_payload(request))
    workflow = _workflow_record(response_payload)
    summary = _workflow_summary(workflow)
    if summary:
        yield encode_sse(
            "TEXT_MESSAGE_CONTENT",
            {
                "type": "TEXT_MESSAGE_CONTENT",
                "threadId": request.thread_id,
                "runId": request.run_id,
                "delta": summary,
            },
        )

    yield encode_sse(
        "STATE_DELTA",
        {
            "type": "STATE_DELTA",
            "threadId": request.thread_id,
            "runId": request.run_id,
            "delta": {"workflow": workflow},
        },
    )

    approval_event = _approval_event(workflow)
    if approval_event is not None:
        yield encode_sse(
            "CUSTOM",
            {
                "type": "CUSTOM",
                "name": "hitl.approval.requested",
                "threadId": request.thread_id,
                "runId": request.run_id,
                "value": approval_event,
            },
        )

    yield encode_sse(
        "RUN_FINISHED",
        {
            "type": "RUN_FINISHED",
            "threadId": request.thread_id,
            "runId": request.run_id,
        },
    )


def _workflow_plan_payload(request: RunAgentInput) -> dict[str, Any]:
    state = request.state
    return {
        "question": _latest_user_text(request),
        "user_id": state.get("user_id", "sample-user"),
        "session_id": state.get("session_id", request.thread_id),
        "tenant_id": state.get("tenant_id"),
        "auth_context_ref": state.get("auth_context_ref"),
        "token_ref": state.get("token_ref"),
        "token_scopes": state.get("token_scopes", []),
        "allowed_tools": state.get("allowed_tools"),
    }


def _latest_user_text(request: RunAgentInput) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            text = _message_content_text(message.content)
            if text:
                return text
    return "Plan workflow"


def _message_content_text(content: str | list[dict[str, Any]] | None) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(part.get("text", "")).strip()
            for part in content
            if part.get("type") == "text" and part.get("text")
        ]
        return " ".join(part for part in parts if part)
    return ""


def _workflow_summary(workflow: dict[str, Any]) -> str:
    workflow_id = workflow.get("workflow_id", "workflow")
    status = _workflow_status(workflow)
    step_count = len(_workflow_steps(workflow))
    return f"Workflow {workflow_id} is {status} with {step_count} planned step(s)."


def _approval_event(workflow: dict[str, Any]) -> dict[str, Any] | None:
    if _workflow_status(workflow) != "awaiting_approval":
        return None
    policy = workflow.get("policy", {})
    policy_payload = cast(dict[str, Any], policy) if isinstance(policy, dict) else {}
    authorization = workflow.get("authorization", {})
    authorization_payload = (
        cast(dict[str, Any], authorization) if isinstance(authorization, dict) else {}
    )
    return {
        "kind": "HITL_APPROVAL",
        "workflow_id": workflow.get("workflow_id"),
        "plan_hash": workflow.get("plan_hash"),
        "required_scopes": policy_payload.get(
            "required_scopes",
            authorization_payload.get("scopes", []),
        ),
        "message": policy_payload.get(
            "human_description",
            "Workflow manifest is awaiting human approval.",
        ),
    }


def _workflow_record(payload: dict[str, Any]) -> dict[str, Any]:
    workflow = payload.get("workflow")
    return cast(dict[str, Any], workflow) if isinstance(workflow, dict) else payload


def _workflow_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    proposal = workflow.get("proposal", workflow.get("plan", {}))
    if not isinstance(proposal, dict):
        return []
    raw_steps_value = cast(dict[str, Any], proposal).get("steps", [])
    if not isinstance(raw_steps_value, list):
        return []
    raw_steps = cast(list[object], raw_steps_value)
    return [cast(dict[str, Any], step) for step in raw_steps if isinstance(step, dict)]


def _workflow_status(workflow: dict[str, Any]) -> str:
    status = workflow.get("status", "planned")
    if isinstance(status, dict):
        status_payload = cast(dict[str, Any], status)
        value = status_payload.get("status")
        return value if isinstance(value, str) else "planned"
    return status if isinstance(status, str) else "planned"

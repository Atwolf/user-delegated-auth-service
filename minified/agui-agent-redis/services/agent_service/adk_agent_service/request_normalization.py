from __future__ import annotations

from typing import Any

from ag_ui.core import RunAgentInput

from adk_agent_service.contracts import AgentRunRequest, UserContext


def agent_run_request_from_agui(
    input_data: RunAgentInput,
    user_context: UserContext,
) -> AgentRunRequest:
    return AgentRunRequest(
        threadId=input_data.thread_id,
        runId=input_data.run_id,
        parentRunId=input_data.parent_run_id,
        sessionId=input_data.thread_id,
        messages=[model_json(message) for message in input_data.messages],
        tools=[model_json(tool) for tool in input_data.tools],
        context=[model_json(context) for context in input_data.context],
        state=state_without_client_session(input_data.state),
        forwardedProps=input_data.forwarded_props,
        user=user_context,
    )


def state_without_client_session(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: state_value
        for key, state_value in value.items()
        if key not in {"sessionId", "session_id"}
    }


def model_json(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        return value
    return dict(value)

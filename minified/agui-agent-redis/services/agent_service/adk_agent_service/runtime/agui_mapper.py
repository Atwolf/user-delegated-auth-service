from __future__ import annotations

from typing import Any, cast

from ag_ui.core import BaseEvent, Context, EventType, Message, RunAgentInput, StateDeltaEvent, Tool
from pydantic import TypeAdapter

from adk_agent_service.contracts import AgentRunRequest, ThreadRunMetadata

_MESSAGES_ADAPTER = TypeAdapter(list[Message])
_TOOLS_ADAPTER = TypeAdapter(list[Tool])
_CONTEXT_ADAPTER = TypeAdapter(list[Context])


def to_agui_input(request: AgentRunRequest, metadata: ThreadRunMetadata) -> RunAgentInput:
    thread_metadata = {
        "threadId": metadata.thread_id,
        "sessionId": metadata.session_id,
        "agentSessionId": metadata.agent_session_id,
        "updatedAt": metadata.updated_at,
    }
    user_state = {
        "userId": request.user.user_id,
        "authScheme": request.user.auth_scheme,
    }
    return RunAgentInput(
        thread_id=request.thread_id,
        run_id=request.run_id,
        parent_run_id=request.parent_run_id,
        state={**request.state, "threadMetadata": thread_metadata, "user": user_state},
        messages=agui_messages(request),
        tools=_TOOLS_ADAPTER.validate_python(request.tools),
        context=_CONTEXT_ADAPTER.validate_python(request.context),
        forwarded_props={
            **dict_or_empty(request.forwarded_props),
            "threadMetadata": thread_metadata,
            "user": user_state,
        },
    )


def agui_messages(request: AgentRunRequest) -> list[Message]:
    messages: list[dict[str, Any]] = []
    for index, message in enumerate(request.messages):
        item = message.model_dump(mode="json", by_alias=True, exclude_none=True)
        item.setdefault("id", f"{request.run_id}:message:{index}")
        messages.append(item)
    if not messages:
        messages.append(
            {
                "id": f"{request.run_id}:message:0",
                "role": "user",
                "content": "Run the agent.",
            }
        )
    return _MESSAGES_ADAPTER.validate_python(messages)


def thread_metadata_delta(metadata: ThreadRunMetadata) -> StateDeltaEvent:
    return StateDeltaEvent(
        type=EventType.STATE_DELTA,
        delta=[
            {
                "op": "add",
                "path": "/threadMetadata",
                "value": {
                    "threadId": metadata.thread_id,
                    "sessionId": metadata.session_id,
                    "agentSessionId": metadata.agent_session_id,
                    "updatedAt": metadata.updated_at,
                },
            }
        ],
    )


def user_id_from_agui_input(input_data: RunAgentInput) -> str:
    state = input_data.state if isinstance(input_data.state, dict) else {}
    user = state.get("user")
    if isinstance(user, dict):
        user_id = user.get("userId")
        if isinstance(user_id, str) and user_id:
            return user_id
    raise RuntimeError("AG-UI state is missing user.userId")


def event_type(event: BaseEvent) -> str:
    value = getattr(event, "type", "")
    if isinstance(value, EventType):
        return value.value
    return str(value)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}

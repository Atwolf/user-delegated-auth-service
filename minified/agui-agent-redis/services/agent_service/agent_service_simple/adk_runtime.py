from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any, cast

from ag_ui.core import BaseEvent, Context, EventType, Message, RunAgentInput, StateDeltaEvent, Tool
from pydantic import TypeAdapter

from agent_service_simple.models import AgentRunRequest, ThreadCacheEntry

APP_NAME = "magnum_opus_minified_agent_service"

_MESSAGES_ADAPTER = TypeAdapter(list[Message])
_TOOLS_ADAPTER = TypeAdapter(list[Tool])
_CONTEXT_ADAPTER = TypeAdapter(list[Context])


class PersistentAdkRuntime:
    """Process-scoped AG-UI/ADK runtime with a single execution path."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._agui_adk_agent: object | None = None

    async def stream_events(
        self,
        request: AgentRunRequest,
        cache_key: str,
        cache_entry: ThreadCacheEntry,
    ) -> AsyncIterator[BaseEvent]:
        lock = self._locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cache_delta_sent = False
            async for event in self._ensure_agui_adk_agent().run(
                _to_agui_input(request, cache_entry)
            ):
                yield event
                if not cache_delta_sent and _event_type(event) == EventType.RUN_STARTED.value:
                    yield _cache_delta(cache_key, cache_entry)
                    cache_delta_sent = True

    def _ensure_agui_adk_agent(self) -> Any:
        if self._agui_adk_agent is not None:
            return self._agui_adk_agent

        try:
            from ag_ui_adk import ADKAgent
            from google.adk.agents import Agent
        except ImportError as exc:
            raise RuntimeError("ag_ui_adk and google-adk are required") from exc

        self._agui_adk_agent = ADKAgent(
            adk_agent=Agent(
                name="minified_adk_agent",
                model=_model(),
                instruction=(
                    "Respond directly to the user. Use the AG-UI state as thread context. "
                    "Redis contains cache metadata only; ADK is the only agent runtime."
                ),
            ),
            app_name=APP_NAME,
            user_id_extractor=_user_id_from_agui_input,
            use_in_memory_services=True,
            use_thread_id_as_session_id=True,
            capabilities={
                "transport": {"streaming": True},
                "state": {"shared": True},
                "custom": {"redisThreadCache": True},
            },
        )
        return self._agui_adk_agent


def _model() -> object:
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from google.adk.models.anthropic_llm import AnthropicLlm
        except ImportError as exc:
            raise RuntimeError("google-adk Anthropic support is not installed") from exc
        return AnthropicLlm(model=os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-20250514")
    return os.getenv("GOOGLE_ADK_MODEL") or "gemini-flash-latest"


def _to_agui_input(request: AgentRunRequest, cache_entry: ThreadCacheEntry) -> RunAgentInput:
    cache_state = {
        "threadId": cache_entry.thread_id,
        "sessionId": cache_entry.session_id,
        "agentSessionId": cache_entry.agent_session_id,
        "runCount": cache_entry.run_count,
        "updatedAt": cache_entry.updated_at,
    }
    user_state = {
        "userId": request.user.user_id,
        "tokenRef": request.user.token_ref,
        "authScheme": request.user.auth_scheme,
    }
    return RunAgentInput(
        thread_id=request.thread_id,
        run_id=request.run_id,
        parent_run_id=request.parent_run_id,
        state={**request.state, "cache": cache_state, "user": user_state},
        messages=_agui_messages(request),
        tools=_TOOLS_ADAPTER.validate_python(request.tools),
        context=_CONTEXT_ADAPTER.validate_python(request.context),
        forwarded_props={
            **_dict_or_empty(request.forwarded_props),
            "cache": cache_state,
            "user": user_state,
        },
    )


def _agui_messages(request: AgentRunRequest) -> list[Message]:
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


def _cache_delta(cache_key: str, cache_entry: ThreadCacheEntry) -> StateDeltaEvent:
    return StateDeltaEvent(
        type=EventType.STATE_DELTA,
        delta=[
            {
                "op": "add",
                "path": "/cache",
                "value": {
                    "key": cache_key,
                    "threadId": cache_entry.thread_id,
                    "sessionId": cache_entry.session_id,
                    "agentSessionId": cache_entry.agent_session_id,
                    "runCount": cache_entry.run_count,
                    "updatedAt": cache_entry.updated_at,
                },
            }
        ],
    )


def _user_id_from_agui_input(input_data: RunAgentInput) -> str:
    state = input_data.state if isinstance(input_data.state, dict) else {}
    user = state.get("user")
    if isinstance(user, dict):
        user_id = user.get("userId")
        if isinstance(user_id, str) and user_id:
            return user_id
    raise RuntimeError("AG-UI state is missing user.userId")


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _event_type(event: BaseEvent) -> str:
    value = getattr(event, "type", "")
    if isinstance(value, EventType):
        return value.value
    return str(value)

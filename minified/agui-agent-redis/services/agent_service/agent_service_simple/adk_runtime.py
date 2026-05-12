from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

from ag_ui.core import (
    BaseEvent,
    Context,
    EventType,
    Message,
    RunAgentInput,
    RunFinishedEvent,
    RunStartedEvent,
    StateDeltaEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    Tool,
)
from pydantic import TypeAdapter

from agent_service_simple.models import AgentRunRequest, RuntimeResponse, ThreadCacheEntry

APP_NAME = "magnum_opus_minified_agent_service"

_MESSAGES_ADAPTER = TypeAdapter(list[Message])
_TOOLS_ADAPTER = TypeAdapter(list[Tool])
_CONTEXT_ADAPTER = TypeAdapter(list[Context])


@dataclass
class StatefulSubagent:
    name: str
    description: str
    handled_turns: int = 0

    async def run(self, request: AgentRunRequest, cache_entry: ThreadCacheEntry) -> str:
        self.handled_turns += 1
        latest = latest_user_text(request)
        return (
            f"{self.name} handled turn {cache_entry.run_count} for thread "
            f"{cache_entry.thread_id}. Latest user input: {latest}"
        )


class PersistentAdkRuntime:
    """Process-scoped AG-UI/ADK runtime.

    Live mode delegates event translation to the official ``ag_ui_adk.ADKAgent`` bridge.
    Local mode remains deterministic, but still emits typed AG-UI events through the same
    server encoder path so the client contract is identical without provider credentials.
    """

    def __init__(self) -> None:
        self._mode = os.getenv("AGENT_SERVICE_RUNTIME_MODE", "local").strip().lower()
        self._locks: dict[str, asyncio.Lock] = {}
        self._subagents = {
            "support_agent": StatefulSubagent(
                name="support_agent",
                description="Handles explanatory and troubleshooting requests.",
            ),
            "operations_agent": StatefulSubagent(
                name="operations_agent",
                description="Handles runtime, cache, and service-boundary requests.",
            ),
        }
        self._agui_adk_agent: object | None = None

    async def stream_events(
        self,
        request: AgentRunRequest,
        cache_key: str,
        cache_entry: ThreadCacheEntry,
    ) -> AsyncIterator[BaseEvent]:
        lock = self._locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            if self._should_use_live_adk():
                async for event in self._stream_live_adk(request, cache_key, cache_entry):
                    yield event
                return

            async for event in self._stream_local(request, cache_key, cache_entry):
                yield event

    async def _stream_local(
        self,
        request: AgentRunRequest,
        cache_key: str,
        cache_entry: ThreadCacheEntry,
    ) -> AsyncIterator[BaseEvent]:
        response = await self._run_local(request, cache_entry)
        message_id = f"{request.run_id}:assistant"
        yield RunStartedEvent(
            type=EventType.RUN_STARTED,
            thread_id=request.thread_id,
            run_id=request.run_id,
        )
        yield self._cache_delta(cache_key, cache_entry, response)
        yield TextMessageStartEvent(
            type=EventType.TEXT_MESSAGE_START,
            message_id=message_id,
            role="assistant",
        )
        for chunk in _chunk_text(response.text):
            yield TextMessageContentEvent(
                type=EventType.TEXT_MESSAGE_CONTENT,
                message_id=message_id,
                delta=chunk,
            )
            await asyncio.sleep(0)
        yield TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=message_id)
        yield RunFinishedEvent(
            type=EventType.RUN_FINISHED,
            thread_id=request.thread_id,
            run_id=request.run_id,
        )

    async def _stream_live_adk(
        self,
        request: AgentRunRequest,
        cache_key: str,
        cache_entry: ThreadCacheEntry,
    ) -> AsyncIterator[BaseEvent]:
        agent = self._ensure_agui_adk_agent()
        input_data = _to_agui_input(request, cache_entry)
        cache_delta_sent = False
        runtime_response = RuntimeResponse(
            text="",
            routed_agent="adk_coordinator",
            runtime_mode="adk",
        )

        async for event in agent.run(input_data):
            yield event
            if not cache_delta_sent and _event_type(event) == EventType.RUN_STARTED.value:
                yield self._cache_delta(cache_key, cache_entry, runtime_response)
                cache_delta_sent = True

    async def _run_local(
        self,
        request: AgentRunRequest,
        cache_entry: ThreadCacheEntry,
    ) -> RuntimeResponse:
        routed_agent = self._route(request)
        text = await self._subagents[routed_agent].run(request, cache_entry)
        return RuntimeResponse(text=text, routed_agent=routed_agent, runtime_mode="local")

    def _route(self, request: AgentRunRequest) -> str:
        text = latest_user_text(request).casefold()
        if any(token in text for token in ("redis", "cache", "container", "service", "runtime")):
            return "operations_agent"
        return "support_agent"

    def _should_use_live_adk(self) -> bool:
        if self._mode in {"local", "mock", "deterministic"}:
            return False
        if self._mode == "adk":
            return True
        return bool(
            os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("GOOGLE_CLOUD_PROJECT")
            or os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").casefold() == "true"
        )

    def _ensure_agui_adk_agent(self) -> Any:
        if self._agui_adk_agent is not None:
            return self._agui_adk_agent

        try:
            from ag_ui_adk import ADKAgent
            from google.adk.agents import Agent
        except ImportError as exc:
            raise RuntimeError("ag_ui_adk and google-adk are required for live ADK mode") from exc

        model = self._model()
        support_agent = Agent(
            name="support_agent",
            model=model,
            description="Explains behavior and answers product-support questions.",
            instruction="Answer the user clearly using only the provided thread context.",
        )
        operations_agent = Agent(
            name="operations_agent",
            model=model,
            description="Handles runtime, Redis cache, and service-boundary questions.",
            instruction="Focus on concrete service-boundary, cache, and runtime details.",
        )
        coordinator = Agent(
            name="coordinator_dispatcher",
            model=model,
            description="Routes requests to stateful specialist subagents.",
            instruction=(
                "You are the coordinator dispatcher. Use the Redis-backed thread context "
                "from AG-UI state and route to the most relevant specialist. Preserve the "
                "service boundary: Redis is cache state, ADK is execution state, and AG-UI "
                "is the event API. Keep the response concise."
            ),
            sub_agents=[support_agent, operations_agent],
        )
        self._agui_adk_agent = ADKAgent(
            adk_agent=coordinator,
            app_name=APP_NAME,
            user_id_extractor=_user_id_from_agui_input,
            use_in_memory_services=True,
            use_thread_id_as_session_id=True,
            capabilities={
                "transport": {"streaming": True},
                "state": {"shared": True},
                "multiAgent": {"routing": "coordinator_dispatcher"},
                "custom": {"redisThreadCache": True},
            },
        )
        return self._agui_adk_agent

    def _model(self) -> object:
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                from google.adk.models.anthropic_llm import AnthropicLlm
            except ImportError as exc:
                raise RuntimeError("google-adk Anthropic support is not installed") from exc
            return AnthropicLlm(
                model=os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-20250514"
            )
        return os.getenv("GOOGLE_ADK_MODEL") or "gemini-flash-latest"

    def _cache_delta(
        self,
        cache_key: str,
        cache_entry: ThreadCacheEntry,
        runtime_response: RuntimeResponse,
    ) -> StateDeltaEvent:
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
                        "routedAgent": runtime_response.routed_agent,
                        "runtimeMode": runtime_response.runtime_mode,
                    },
                }
            ],
        )


def latest_user_text(request: AgentRunRequest) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            return _message_text(message.content) or "Run the agent."
    return "Run the agent."


def _to_agui_input(request: AgentRunRequest, cache_entry: ThreadCacheEntry) -> RunAgentInput:
    state = {
        **request.state,
        "cache": {
            "threadId": cache_entry.thread_id,
            "sessionId": cache_entry.session_id,
            "agentSessionId": cache_entry.agent_session_id,
            "runCount": cache_entry.run_count,
            "updatedAt": cache_entry.updated_at,
        },
        "user": {
            "userId": request.user.user_id,
            "tokenRef": request.user.token_ref,
            "authScheme": request.user.auth_scheme,
        },
    }
    forwarded_props = {
        **_dict_or_empty(request.forwarded_props),
        "cache": state["cache"],
        "user": state["user"],
    }
    return RunAgentInput(
        thread_id=request.thread_id,
        run_id=request.run_id,
        parent_run_id=request.parent_run_id,
        state=state,
        messages=_agui_messages(request),
        tools=_TOOLS_ADAPTER.validate_python(request.tools),
        context=_CONTEXT_ADAPTER.validate_python(request.context),
        forwarded_props=forwarded_props,
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


def _user_id_from_agui_input(input_data: RunAgentInput) -> str:
    state = input_data.state if isinstance(input_data.state, dict) else {}
    user = state.get("user")
    if isinstance(user, dict):
        user_id = user.get("userId") or user.get("user_id")
        if isinstance(user_id, str) and user_id:
            return user_id
    return f"thread_user_{input_data.thread_id}"


def _message_text(content: str | list[dict[str, Any]] | None) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(
            str(part.get("text", "")).strip()
            for part in content
            if part.get("type") == "text" and part.get("text")
        ).strip()
    return ""


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _chunk_text(text: str, *, max_chars: int = 48) -> list[str]:
    if not text:
        return ["The local runtime completed without textual output."]

    chunks: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(f"{current} ")
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _event_type(event: BaseEvent) -> str:
    value = getattr(event, "type", "")
    if isinstance(value, EventType):
        return value.value
    return str(value)

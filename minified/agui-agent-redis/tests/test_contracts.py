from __future__ import annotations

import json
import sys
import types
from typing import Any

from adk_agent_service.contracts import AgentRunRequest, ThreadRunMetadata, UserContext
from adk_agent_service.stores.thread_metadata import thread_metadata_key
from ag_ui.core import (
    EventType,
    RunAgentInput,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from ag_ui.encoder import EventEncoder
from gateway_app.auth import bearer_token
from gateway_app.forwarding import agent_service_payload
from gateway_app.schemas import RunAgentInput as GatewayRunAgentInput
from gateway_app.schemas import UserContext as GatewayUserContext


def test_thread_metadata_key_uses_colon_namespace_and_url_encoding() -> None:
    assert (
        thread_metadata_key(user_id="user:1", thread_id="thread/1")
        == "agui:agent:v1:user:user%3A1:thread:thread%2F1"
    )


def test_bearer_token_extraction_requires_bearer_scheme() -> None:
    assert bearer_token("Bearer abc") == "abc"
    assert bearer_token("Basic abc") is None
    assert bearer_token(None) is None


def test_gateway_derives_agent_session_from_thread_and_strips_client_session() -> None:
    payload = GatewayRunAgentInput(
        threadId="thread-001",
        runId="run-001",
        messages=[],
        state={"sessionId": "client-choice", "session_id": "client-choice", "topic": "demo"},
    )

    forwarded = agent_service_payload(payload, GatewayUserContext(user_id="user-001"))

    assert forwarded["sessionId"] == "thread-001"
    assert forwarded["state"] == {"topic": "demo"}
    assert forwarded["user"] == {"user_id": "user-001", "auth_scheme": "bearer"}


async def test_agent_service_stream_uses_adk_events_and_cache_delta(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    adk_bridge_module = types.ModuleType("ag_ui_adk")
    adk_bridge_module.ADKAgent = _RecordingADKAgentBridge
    adk_agents_module = types.ModuleType("google.adk.agents")
    adk_agents_module.Agent = _RecordingGoogleAgent
    monkeypatch.setitem(sys.modules, "ag_ui_adk", adk_bridge_module)
    monkeypatch.setitem(sys.modules, "google.adk.agents", adk_agents_module)

    import adk_agent_service.app as agent_app

    _RecordingADKAgentBridge.instances.clear()

    payload = AgentRunRequest(
        threadId="thread-001",
        runId="run-001",
        sessionId="thread-001",
        messages=[
            {
                "id": "msg-001",
                "role": "user",
                "content": "Confirm ADK streaming and show the thread metadata.",
            }
        ],
        state={},
        user=UserContext(user_id="user-001"),
    )

    events = [
        _decode_sse(frame)
        async for frame in agent_app.run_stream(
            payload,
            _MemoryMetadataStore(),
            EventEncoder(),
        )
    ]

    assert len(_RecordingADKAgentBridge.instances) == 1
    assert _RecordingADKAgentBridge.instances[0].kwargs["adk_agent"].kwargs["name"] == (
        "agui_adk_agent"
    )
    assert [event["type"] for event in events][:3] == [
        "RUN_STARTED",
        "STATE_DELTA",
        "TEXT_MESSAGE_START",
    ]
    assert [event["type"] for event in events][-2:] == [
        "TEXT_MESSAGE_END",
        "RUN_FINISHED",
    ]
    assert sum(event["type"] == "TEXT_MESSAGE_CONTENT" for event in events) == 2
    state_delta = next(event for event in events if event["type"] == "STATE_DELTA")
    assert set(state_delta["delta"][0]["value"]) == {
        "agentSessionId",
        "sessionId",
        "threadId",
        "updatedAt",
    }


class _RecordingGoogleAgent:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _RecordingADKAgentBridge:
    instances: list[_RecordingADKAgentBridge] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.instances.append(self)

    async def run(self, input_data: RunAgentInput):
        assert input_data.state["threadMetadata"]["threadId"] == "thread-001"
        assert input_data.state["user"]["userId"] == "user-001"
        message_id = "adk-message"
        yield RunStartedEvent(
            type=EventType.RUN_STARTED,
            thread_id=input_data.thread_id,
            run_id=input_data.run_id,
        )
        yield TextMessageStartEvent(
            type=EventType.TEXT_MESSAGE_START,
            message_id=message_id,
            role="assistant",
        )
        yield TextMessageContentEvent(
            type=EventType.TEXT_MESSAGE_CONTENT,
            message_id=message_id,
            delta="chunk one ",
        )
        yield TextMessageContentEvent(
            type=EventType.TEXT_MESSAGE_CONTENT,
            message_id=message_id,
            delta="chunk two",
        )
        yield TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=message_id)
        yield RunFinishedEvent(
            type=EventType.RUN_FINISHED,
            thread_id=input_data.thread_id,
            run_id=input_data.run_id,
        )


class _MemoryMetadataStore:
    async def upsert_from_run(self, payload: AgentRunRequest) -> tuple[str, ThreadRunMetadata]:
        return (
            "redis-entry",
            ThreadRunMetadata(
                user_id=payload.user.user_id,
                thread_id=payload.thread_id,
                session_id=payload.session_id,
                agent_session_id="agent-session",
            ),
        )


def _decode_sse(frame: str) -> dict[str, Any]:
    data = "".join(
        line.removeprefix("data:").strip()
        for line in frame.splitlines()
        if line.startswith("data:")
    )
    return json.loads(data)

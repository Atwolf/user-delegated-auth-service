from __future__ import annotations

import json
import sys
import types
from typing import Any

from adk_agent_service.auth import bearer_token
from adk_agent_service.contracts import AgentRunRequest, ThreadRunMetadata, UserContext
from adk_agent_service.request_normalization import agent_run_request_from_agui
from adk_agent_service.stores.in_memory_thread_metadata import InMemoryThreadMetadataStore
from adk_agent_service.stores.redis_thread_metadata import RedisThreadMetadataStore
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
from fastapi.testclient import TestClient


def test_thread_metadata_key_uses_colon_namespace_and_url_encoding() -> None:
    assert (
        thread_metadata_key(user_id="user:1", thread_id="thread/1")
        == "agui:agent:v1:user:user%3A1:thread:thread%2F1"
    )


def test_bearer_token_extraction_requires_bearer_scheme() -> None:
    assert bearer_token("Bearer abc") == "abc"
    assert bearer_token("Basic abc") is None
    assert bearer_token(None) is None


def test_agent_request_derives_session_from_thread_and_strips_client_session() -> None:
    input_data = RunAgentInput(
        threadId="thread-001",
        runId="run-001",
        messages=[],
        tools=[],
        context=[],
        state={"sessionId": "client-choice", "session_id": "client-choice", "topic": "demo"},
        forwardedProps={},
    )

    payload = agent_run_request_from_agui(input_data, UserContext(user_id="user-001"))

    assert payload.session_id == "thread-001"
    assert payload.state == {"topic": "demo"}
    assert payload.user == UserContext(user_id="user-001")


def test_agent_endpoint_requires_bearer_and_user_id() -> None:
    from adk_agent_service.app import create_app

    client = TestClient(create_app(metadata_store=InMemoryThreadMetadataStore()))
    body = agui_request_body()

    missing_token = client.post("/agent", json=body, headers={"X-User-Id": "user-001"})
    assert missing_token.status_code == 401

    missing_user = client.post(
        "/agent",
        json=body,
        headers={"Authorization": "Bearer demo-token"},
    )
    assert missing_user.status_code == 401


async def test_redis_store_writes_thread_metadata() -> None:
    payload = agent_run_request()
    redis = _RecordingRedis()
    store = RedisThreadMetadataStore(redis, ttl_seconds=60)

    key, metadata = await store.upsert_from_run(payload)

    assert key == "agui:agent:v1:user:user-001:thread:thread-001"
    assert metadata.user_id == "user-001"
    assert metadata.thread_id == "thread-001"
    assert metadata.session_id == "thread-001"
    assert redis.calls[0]["key"] == key
    assert redis.calls[0]["ex"] == 60
    assert json.loads(redis.calls[0]["value"])["agent_session_id"] == "thread-001"


async def test_in_memory_store_matches_thread_metadata_shape() -> None:
    payload = agent_run_request()
    store = InMemoryThreadMetadataStore()

    key, metadata = await store.upsert_from_run(payload)

    assert key == "agui:agent:v1:user:user-001:thread:thread-001"
    assert metadata.model_dump().keys() == {
        "user_id",
        "thread_id",
        "session_id",
        "agent_session_id",
        "updated_at",
    }


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

    payload = agent_run_request()

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
        assert "sessionId" not in input_data.state
        assert "session_id" not in input_data.state
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


class _RecordingRedis:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def set(self, key: str, value: str, *, ex: int | None = None) -> object:
        self.calls.append({"key": key, "value": value, "ex": ex})
        return True


def agent_run_request() -> AgentRunRequest:
    return AgentRunRequest(
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


def agui_request_body() -> dict[str, Any]:
    return {
        "threadId": "thread-001",
        "runId": "run-001",
        "messages": [{"id": "msg-001", "role": "user", "content": "Hello"}],
        "tools": [],
        "context": [],
        "state": {},
        "forwardedProps": {},
    }


def _decode_sse(frame: str) -> dict[str, Any]:
    data = "".join(
        line.removeprefix("data:").strip()
        for line in frame.splitlines()
        if line.startswith("data:")
    )
    return json.loads(data)

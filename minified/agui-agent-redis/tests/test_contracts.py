from __future__ import annotations

import json
from typing import Any

from ag_ui.encoder import EventEncoder
from ag_ui_gateway_simple.app import _bearer_token, _claim_from_unverified_jwt, _fingerprint
from agent_service_simple.adk_runtime import PersistentAdkRuntime
from agent_service_simple.cache import thread_cache_key
from agent_service_simple.models import AgentRunRequest, ThreadCacheEntry, UserContext


def test_thread_cache_key_uses_colon_namespace_and_url_encoding() -> None:
    assert (
        thread_cache_key(user_id="user:1", thread_id="thread/1")
        == "agui:min:v1:user:user%3A1:thread:thread%2F1"
    )


def test_bearer_token_extraction_requires_bearer_scheme() -> None:
    assert _bearer_token("Bearer abc") == "abc"
    assert _bearer_token("Basic abc") is None
    assert _bearer_token(None) is None


def test_opaque_token_fingerprint_is_stable() -> None:
    assert _fingerprint("token") == _fingerprint("token")
    assert _fingerprint("token") != _fingerprint("other")


def test_unverified_jwt_claim_extraction_is_best_effort() -> None:
    token = "header.eyJzdWIiOiAidXNlci0xIn0.signature"
    assert _claim_from_unverified_jwt(token, ("sub",)) == "user-1"
    assert _claim_from_unverified_jwt("not-a-jwt", ("sub",)) is None


async def test_agent_service_stream_uses_agui_events_and_chunked_content(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENT_SERVICE_RUNTIME_MODE", "local")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    from agent_service_simple.app import _run_stream

    payload = AgentRunRequest(
        threadId="thread-001",
        runId="run-001",
        sessionId="thread-001",
        messages=[
            {
                "id": "msg-001",
                "role": "user",
                "content": "Show me the Redis-backed thread state path.",
            }
        ],
        state={},
        user=UserContext(user_id="user-001", token_ref="sha256:token"),
    )

    events = [
        _decode_sse(frame)
        async for frame in _run_stream(
            payload,
            _FakeCache(),
            PersistentAdkRuntime(),
            EventEncoder(),
        )
    ]

    assert [event["type"] for event in events][:3] == [
        "RUN_STARTED",
        "STATE_DELTA",
        "TEXT_MESSAGE_START",
    ]
    assert [event["type"] for event in events][-2:] == [
        "TEXT_MESSAGE_END",
        "RUN_FINISHED",
    ]
    assert sum(event["type"] == "TEXT_MESSAGE_CONTENT" for event in events) > 1
    state_delta = next(event for event in events if event["type"] == "STATE_DELTA")
    assert state_delta["delta"][0]["value"]["key"] == "cache-key"


class _FakeCache:
    async def upsert_from_run(self, payload: AgentRunRequest) -> tuple[str, ThreadCacheEntry]:
        return (
            "cache-key",
            ThreadCacheEntry(
                user_id=payload.user.user_id,
                thread_id=payload.thread_id,
                session_id=payload.session_id,
                agent_session_id="agent-session",
                token_ref=payload.user.token_ref,
                run_count=1,
            ),
        )


def _decode_sse(frame: str) -> dict[str, Any]:
    data = "".join(
        line.removeprefix("data:").strip()
        for line in frame.splitlines()
        if line.startswith("data:")
    )
    return json.loads(data)

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from gateway_app.schemas import RunAgentInput, UserContext

DEFAULT_AGENT_SERVICE_URL = "http://agent-service:8090"


async def forward_agent_run(
    payload: RunAgentInput,
    user_context: UserContext,
) -> AsyncIterator[str]:
    try:
        async with httpx.AsyncClient(
            base_url=agent_service_url(),
            timeout=httpx.Timeout(connect=5.0, read=None, write=10.0, pool=5.0),
        ) as client:
            async with client.stream(
                "POST",
                "/runs/stream",
                json=agent_service_payload(payload, user_context),
                headers={"Accept": "text/event-stream"},
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_text():
                    if chunk:
                        yield chunk
    except Exception as exc:
        yield encode_sse(
            {
                "type": "RUN_ERROR",
                "message": safe_error(exc),
                "code": "AGENT_SERVICE_FORWARDING_ERROR",
            }
        )


def agent_service_payload(payload: RunAgentInput, user_context: UserContext) -> dict[str, Any]:
    return {
        "threadId": payload.thread_id,
        "runId": payload.run_id,
        "parentRunId": payload.parent_run_id,
        "sessionId": payload.thread_id,
        "messages": [
            message.model_dump(mode="json", by_alias=True, exclude_none=True)
            for message in payload.messages
        ],
        "tools": payload.tools,
        "context": payload.context,
        "state": state_without_client_session(payload),
        "forwardedProps": payload.forwarded_props,
        "user": user_context.model_dump(mode="json"),
    }


def state_without_client_session(payload: RunAgentInput) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.state.items()
        if key not in {"sessionId", "session_id"}
    }


def agent_service_url() -> str:
    return (os.getenv("AGENT_SERVICE_URL") or DEFAULT_AGENT_SERVICE_URL).rstrip("/")


def safe_error(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    return message.replace("\n", " ")[:240]


def encode_sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'), sort_keys=True)}\n\n"

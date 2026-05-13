from __future__ import annotations

import hashlib
import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

DEFAULT_AGENT_SERVICE_URL = "http://agent-service:8090"


class AgUiMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    role: str | None = None
    content: str | list[dict[str, Any]] | None = None


class RunAgentInput(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    thread_id: str = Field(..., validation_alias=AliasChoices("threadId", "thread_id"))
    run_id: str = Field(..., validation_alias=AliasChoices("runId", "run_id"))
    parent_run_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("parentRunId", "parent_run_id"),
    )
    messages: list[AgUiMessage] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    context: list[dict[str, Any]] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    forwarded_props: Any = Field(
        default_factory=dict,
        validation_alias=AliasChoices("forwardedProps", "forwarded_props"),
    )


class UserContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    token_ref: str
    auth_scheme: str = "bearer"


def create_app() -> FastAPI:
    app = FastAPI(title="Minified AG-UI Gateway")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/agent/capabilities")
    async def capabilities() -> dict[str, object]:
        return {
            "service": "ag-ui-gateway-simple",
            "protocol": "ag-ui",
            "endpoints": ["GET /healthz", "GET /agent/capabilities", "POST /agent"],
            "event_types": [
                "RUN_STARTED",
                "TEXT_MESSAGE_START",
                "TEXT_MESSAGE_CONTENT",
                "TEXT_MESSAGE_END",
                "STATE_DELTA",
                "RUN_FINISHED",
                "RUN_ERROR",
            ],
        }

    @app.post("/agent")
    async def run_agent(payload: RunAgentInput, request: Request) -> StreamingResponse:
        user_context = _user_context_from_request(request)
        return StreamingResponse(
            _forward_agent_run(payload, user_context),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()


async def _forward_agent_run(
    payload: RunAgentInput,
    user_context: UserContext,
) -> AsyncIterator[str]:
    service_payload = {
        "threadId": payload.thread_id,
        "runId": payload.run_id,
        "parentRunId": payload.parent_run_id,
        "sessionId": _session_id(payload),
        "messages": [
            message.model_dump(mode="json", by_alias=True, exclude_none=True)
            for message in payload.messages
        ],
        "tools": payload.tools,
        "context": payload.context,
        "state": payload.state,
        "forwardedProps": payload.forwarded_props,
        "user": user_context.model_dump(mode="json"),
    }
    try:
        async with httpx.AsyncClient(
            base_url=_agent_service_url(),
            timeout=httpx.Timeout(connect=5.0, read=None, write=10.0, pool=5.0),
        ) as client:
            async with client.stream(
                "POST",
                "/runs/stream",
                json=service_payload,
                headers={"Accept": "text/event-stream"},
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_text():
                    if chunk:
                        yield chunk
    except Exception as exc:
        yield _encode_sse(
            {
                "type": "RUN_ERROR",
                "message": _safe_error(exc),
                "code": "AGENT_SERVICE_FORWARDING_ERROR",
            }
        )


def _user_context_from_request(request: Request) -> UserContext:
    token = _bearer_token(request.headers.get("authorization"))
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is required for the minified gateway",
        )

    user_id = request.headers.get("x-user-id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id is required for the minified gateway",
        )
    return UserContext(user_id=user_id, token_ref=f"sha256:{_fingerprint(token)}")


def _bearer_token(value: str | None) -> str | None:
    if value is None:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.casefold() != "bearer" or not token.strip():
        return None
    return token.strip()


def _session_id(payload: RunAgentInput) -> str:
    candidate = payload.state.get("sessionId") or payload.state.get("session_id")
    return candidate if isinstance(candidate, str) and candidate else payload.thread_id


def _agent_service_url() -> str:
    return (os.getenv("AGENT_SERVICE_URL") or DEFAULT_AGENT_SERVICE_URL).rstrip("/")


def _fingerprint(value: str, *, length: int = 32) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:length]


def _safe_error(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    return message.replace("\n", " ")[:240]


def _encode_sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'), sort_keys=True)}\n\n"

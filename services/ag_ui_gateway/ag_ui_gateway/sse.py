from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

from session_state import TrustedSessionContext, signed_session_context_headers

from ag_ui_gateway.client import AgentServiceClient
from ag_ui_gateway.models import RunAgentInput


def encode_sse(data: dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"), sort_keys=True)
    return f"data: {payload}\n\n"


async def stream_agent_events(
    request: RunAgentInput,
    agent_service: AgentServiceClient,
    context: TrustedSessionContext,
) -> AsyncIterator[str]:
    emitted_started = False
    try:
        async for event in agent_service.stream_run(
            _agent_run_payload(request, context),
            signed_session_context_headers(context, secret=_internal_auth_secret()),
        ):
            emitted_started = emitted_started or event.get("type") == "RUN_STARTED"
            yield encode_sse(_browser_event(event))
    except Exception as exc:
        if not emitted_started:
            yield encode_sse(
                {
                    "type": "RUN_STARTED",
                    "threadId": request.thread_id,
                    "runId": request.run_id,
                }
            )
        yield encode_sse(
            {
                "type": "RUN_ERROR",
                "message": str(exc) or exc.__class__.__name__,
                "code": "AGENT_SERVICE_ERROR",
            }
        )


def _agent_run_payload(request: RunAgentInput, context: TrustedSessionContext) -> dict[str, Any]:
    state = _public_state(request.state)
    return {
        "question": _latest_user_text(request),
        "messages": [message.model_dump(mode="json") for message in request.messages],
        "state": state,
        "allowed_tools": context.allowed_tools,
        "session_id": context.session_id,
        "tenant_id": context.tenant_id,
        "token_ref": context.token_ref,
        "token_scopes": context.token_scopes,
        "user_id": context.user_id,
        "thread_id": request.thread_id,
        "run_id": request.run_id,
    }


def _public_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in state.items()
        if _normalized_private_key(key) not in _BROWSER_PRIVATE_KEYS
    }


_BROWSER_PRIVATE_KEYS = {
    "accesstoken",
    "allowedtools",
    "authcontextref",
    "authorization",
    "bearertoken",
    "clientsecret",
    "credential",
    "idtoken",
    "password",
    "privatekey",
    "rawtoken",
    "refreshtoken",
    "secret",
    "sessionid",
    "tenantid",
    "token",
    "tokenref",
    "tokenscopes",
    "userid",
}


def _browser_event(event: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], _strip_browser_private_keys(event))


def _strip_browser_private_keys(value: object) -> object:
    if isinstance(value, list):
        return [_strip_browser_private_keys(item) for item in cast(list[object], value)]
    if isinstance(value, dict):
        return {
            key: _strip_browser_private_keys(item)
            for key, item in cast(dict[str, object], value).items()
            if _normalized_private_key(key) not in _BROWSER_PRIVATE_KEYS
        }
    return value


def _normalized_private_key(key: str) -> str:
    return "".join(character for character in key.lower() if character.isalnum())


def _internal_auth_secret() -> str:
    import os

    return os.getenv("INTERNAL_SERVICE_AUTH_SECRET") or ""


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

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, TypedDict, cast
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from chainlit_middleware.config import ChainlitMiddlewareSettings
from chainlit_middleware.models import (
    ChainlitApprovalEvent,
    ChainlitForwardResponse,
    ChainlitMessageEvent,
    CopilotConfig,
    CopilotWidgetMetadata,
)

HttpClientFactory = Callable[[], AbstractAsyncContextManager[httpx.AsyncClient]]
AUTH0_SESSION_COOKIE = "magnum_opus_auth0_session"
JsonDict = dict[str, Any]


class ParsedSseEvent(TypedDict):
    event: str
    data: JsonDict


def default_http_client_factory(settings: ChainlitMiddlewareSettings) -> HttpClientFactory:
    @asynccontextmanager
    async def client() -> AsyncGenerator[httpx.AsyncClient]:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as async_client:
            yield async_client

    return client


def create_app(
    settings: ChainlitMiddlewareSettings | None = None,
    http_client_factory: HttpClientFactory | None = None,
) -> FastAPI:
    resolved_settings = settings or ChainlitMiddlewareSettings.from_env()
    app = FastAPI(title="Chainlit Compatibility Middleware")
    app.state.settings = resolved_settings
    app.state.http_client_factory = http_client_factory or default_http_client_factory(
        resolved_settings
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def placeholder_ui() -> str:
        return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Magnum Opus Chainlit Copilot</title>
    <style>
      body {
        font-family: ui-sans-serif, system-ui, sans-serif;
        margin: 0;
        background: #f7f7f8;
        color: #171717;
      }
      main { max-width: 760px; margin: 0 auto; padding: 32px; }
      form { display: grid; gap: 12px; margin-top: 20px; }
      textarea {
        min-height: 120px;
        padding: 12px;
        border: 1px solid #cfcfd6;
        border-radius: 6px;
        font: inherit;
      }
      button {
        width: fit-content;
        border: 0;
        border-radius: 6px;
        background: #0f766e;
        color: white;
        padding: 10px 14px;
        font-weight: 700;
      }
      pre {
        white-space: pre-wrap;
        background: white;
        border: 1px solid #d9d9df;
        border-radius: 6px;
        padding: 12px;
      }
      #approval-panel {
        display: none;
        margin-top: 16px;
        padding: 14px;
        border: 1px solid #d9d9df;
        border-radius: 6px;
        background: white;
      }
      .meta { color: #52525b; font-size: 0.9rem; }
    </style>
  </head>
  <body>
    <main>
      <h1>Chainlit Copilot</h1>
      <form id="chat-form">
        <textarea id="message" aria-label="Chainlit workflow input">
Inspect DNS health for app.example.com
        </textarea>
        <button type="submit">Send</button>
      </form>
      <section id="approval-panel">
        <h2 id="workflow-title">Workflow</h2>
        <p id="workflow-status" class="meta"></p>
        <p id="workflow-description"></p>
        <button id="approve-button" type="button">Approve workflow</button>
      </section>
      <pre id="result">Waiting for workflow request.</pre>
    </main>
    <script>
      const form = document.getElementById("chat-form");
      const result = document.getElementById("result");
      const approvalPanel = document.getElementById("approval-panel");
      const workflowTitle = document.getElementById("workflow-title");
      const workflowStatus = document.getElementById("workflow-status");
      const workflowDescription = document.getElementById("workflow-description");
      const approveButton = document.getElementById("approve-button");
      let latestWorkflow = null;

      function renderWorkflow(payload) {
        latestWorkflow = payload.workflow || null;
        result.textContent = JSON.stringify(payload, null, 2);
        if (!latestWorkflow) {
          approvalPanel.style.display = "none";
          return;
        }
        const status = latestWorkflow.status || "planned";
        workflowTitle.textContent = latestWorkflow.workflow_id;
        workflowStatus.textContent = `${status} | ${latestWorkflow.plan_hash}`;
        workflowDescription.textContent = payload.approval?.message || payload.summary || "";
        approvalPanel.style.display = "block";
        approveButton.disabled = status !== "awaiting_approval";
        approveButton.textContent = status === "awaiting_approval"
          ? "Approve workflow"
          : "Approval not required";
      }

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        result.textContent = "Sending...";
        const response = await fetch("/chainlit/events/message", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            thread_id: "chainlit-browser-thread",
            content: document.getElementById("message").value,
            metadata: { source: "chainlit-placeholder-ui" }
          })
        });
        renderWorkflow(await response.json());
      });
      approveButton.addEventListener("click", async () => {
        if (!latestWorkflow) return;
        result.textContent = "Approving...";
        const response = await fetch("/chainlit/events/approve", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            workflow_id: latestWorkflow.workflow_id,
            plan_hash: latestWorkflow.plan_hash
          })
        });
        renderWorkflow(await response.json());
      });
    </script>
  </body>
</html>"""

    @app.get("/copilot/config", response_model=CopilotConfig)
    async def copilot_config(request: Request) -> CopilotConfig:
        settings = _settings(request)
        return CopilotConfig(
            ag_ui_gateway_url=settings.ag_ui_gateway_url,
            widget=CopilotWidgetMetadata(
                name="Chainlit Copilot",
                mount_id="chainlit-copilot",
                transport="ag-ui",
                events_endpoint="/chainlit/events/message",
            ),
        )

    @app.post("/chainlit/events/message", response_model=ChainlitForwardResponse)
    async def forward_message(
        payload: ChainlitMessageEvent,
        request: Request,
    ) -> ChainlitForwardResponse | JSONResponse:
        settings = _settings(request)
        ag_ui_payload = _to_ag_ui_payload(payload, _session_from_request(request))

        try:
            factory = _http_client_factory(request)
            async with factory() as client:
                response = await client.post(settings.ag_ui_gateway_url, json=ag_ui_payload)
        except httpx.HTTPError:
            return JSONResponse(
                status_code=502,
                content={
                    "thread_id": payload.thread_id,
                    "forwarded": False,
                    "ag_ui_status": None,
                },
            )

        ag_ui_events = _parse_sse_events(response.text)
        workflow = _workflow_from_events(ag_ui_events)
        approval = _approval_from_events(ag_ui_events)
        return ChainlitForwardResponse(
            thread_id=payload.thread_id,
            forwarded=200 <= response.status_code < 300,
            ag_ui_status=response.status_code,
            summary=_summary_from_events(ag_ui_events),
            workflow=workflow,
            approval=approval,
            events=cast(list[dict[str, Any]], ag_ui_events),
        )

    @app.post("/chainlit/events/approve")
    async def approve_workflow(
        payload: ChainlitApprovalEvent,
        request: Request,
    ) -> JSONResponse:
        settings = _settings(request)
        session = _session_from_request(request)
        approved_by = (
            str(session.get("userId"))
            if session and session.get("userId")
            else "chainlit-placeholder-user"
        )

        try:
            factory = _http_client_factory(request)
            async with factory() as client:
                response = await client.post(
                    f"{settings.agent_service_url.rstrip('/')}/workflows/{payload.workflow_id}/approve",
                    json={
                        "approved": True,
                        "approved_by_user_id": approved_by,
                        "plan_hash": payload.plan_hash,
                    },
                )
        except httpx.HTTPError:
            return JSONResponse(
                status_code=502,
                content={"forwarded": False, "agent_service_status": None},
            )

        return JSONResponse(
            status_code=response.status_code,
            content={
                "forwarded": 200 <= response.status_code < 300,
                "agent_service_status": response.status_code,
                **_approval_response_payload(response),
            },
        )

    return app


def _settings(request: Request) -> ChainlitMiddlewareSettings:
    return cast(ChainlitMiddlewareSettings, request.app.state.settings)


def _http_client_factory(request: Request) -> HttpClientFactory:
    return cast(HttpClientFactory, request.app.state.http_client_factory)


def _to_ag_ui_payload(
    payload: ChainlitMessageEvent,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = str(uuid4())
    message = {
        "id": str(uuid4()),
        "role": "user",
        "content": payload.content,
        "metadata": {
            **payload.metadata,
            "chainlit_user_id": payload.user_id,
        },
    }
    state = _ag_ui_state_from_session(session)
    return {
        "thread_id": payload.thread_id,
        "threadId": payload.thread_id,
        "run_id": run_id,
        "runId": run_id,
        "messages": [message],
        "state": state,
    }


def _session_from_request(request: Request) -> JsonDict | None:
    raw_cookie = request.cookies.get(AUTH0_SESSION_COOKIE)
    secret = os.getenv("AUTH0_SESSION_SECRET")
    if not raw_cookie or not secret:
        return None
    try:
        payload, signature = raw_cookie.split(".", 1)
        expected = _base64url(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        loaded: object = json.loads(_base64url_decode(payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(loaded, dict):
        return None
    envelope = cast(JsonDict, loaded)
    value = _json_get(envelope, "value")
    if not isinstance(value, dict):
        return None
    return cast(JsonDict, value)


def _ag_ui_state_from_session(session: JsonDict | None) -> JsonDict:
    if not session:
        return {}
    return {
        "allowed_tools": sorted(set(_string_list(session.get("allowedTools")))),
        "auth_context_ref": session.get("authContextRef"),
        "session_id": session.get("sessionId"),
        "token_ref": session.get("tokenRef"),
        "token_scopes": sorted(set(str(session.get("scope", "")).split())),
        "user_id": session.get("userId"),
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str)]


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _parse_sse_events(body: str) -> list[ParsedSseEvent]:
    events: list[ParsedSseEvent] = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name: str | None = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ").strip()
            elif line.startswith("data: "):
                data_lines.append(line.removeprefix("data: ").strip())
        if not event_name or not data_lines:
            continue
        try:
            decoded: object = json.loads("\n".join(data_lines))
            payload = cast(JsonDict, decoded) if isinstance(decoded, dict) else {"value": decoded}
        except json.JSONDecodeError:
            payload = {"raw": "\n".join(data_lines)}
        events.append({"event": event_name, "data": payload})
    return events


def _workflow_from_events(events: list[ParsedSseEvent]) -> JsonDict | None:
    for event in events:
        data = event["data"]
        delta = _json_get(data, "delta")
        if isinstance(delta, dict):
            delta_payload = cast(JsonDict, delta)
            workflow_value = _json_get(delta_payload, "workflow")
            if not isinstance(workflow_value, dict):
                continue
            workflow = cast(JsonDict, workflow_value)
            return _compact_workflow(workflow)
    return None


def _approval_from_events(events: list[ParsedSseEvent]) -> JsonDict | None:
    for event in events:
        data = event["data"]
        value = _json_get(data, "value")
        if _json_get(data, "name") == "hitl.approval.requested" and isinstance(value, dict):
            return cast(JsonDict, value)
    return None


def _summary_from_events(events: list[ParsedSseEvent]) -> str | None:
    for event in events:
        delta = _json_get(event["data"], "delta")
        if isinstance(delta, str):
            return delta
    return None


def _compact_workflow(workflow: JsonDict) -> JsonDict:
    return {
        "workflow_id": _json_get(workflow, "workflow_id"),
        "status": _workflow_status(workflow),
        "plan_hash": _json_get(workflow, "plan_hash"),
        "policy": _json_get(workflow, "policy"),
        "proposal": _json_get(workflow, "proposal"),
        "tool_intents": _json_get(workflow, "tool_intents", []),
    }


def _workflow_status(workflow: JsonDict) -> str:
    status = _json_get(workflow, "status", "planned")
    if isinstance(status, dict):
        value = _json_get(cast(JsonDict, status), "status")
        return value if isinstance(value, str) else "planned"
    return status if isinstance(status, str) else "planned"


def _approval_response_payload(response: httpx.Response) -> JsonDict:
    try:
        decoded: object = response.json()
    except json.JSONDecodeError:
        return {"error": response.text}
    if not isinstance(decoded, dict):
        return {"payload": decoded}
    payload = cast(JsonDict, decoded)
    workflow = _json_get(payload, "workflow")
    if isinstance(workflow, dict):
        payload["workflow"] = _compact_workflow(cast(JsonDict, workflow))
    return payload


def _json_get(payload: JsonDict, key: str, default: object = None) -> object:
    return cast(object, payload.get(key, default))


app = create_app()

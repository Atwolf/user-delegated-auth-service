from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal, TypeVar, cast
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import SecretStr
from session_state import (
    SESSION_CONTEXT_HEADER,
    SESSION_CONTEXT_SIGNATURE_HEADER,
    InternalAuthError,
    TrustedSessionContext,
    signed_session_context_headers,
    verify_session_context,
)
from token_broker import (
    Auth0OnBehalfOfClient,
    Auth0OnBehalfOfConfig,
    WorkflowTokenExchangeRequest,
    WorkflowTokenExchangeResponse,
)
from workflow_core import (
    ApprovedWorkflow,
    ExecutionGrant,
    ToolIntent,
    WorkflowPlan,
    get_tool_authorization,
    plan_hash,
    sign_execution_grant,
)

from .models import (
    AgentDescriptor,
    AgentListResponse,
    PlanWorkflowRequest,
    PlanWorkflowResponse,
    RunAgentRequest,
    SanitizedWorkflowContext,
    ThreadCreateRequest,
    ThreadRecord,
    ThreadResponse,
    TokenContextRegistrationRequest,
    TokenRegistryRecord,
    WorkflowApprovalRequest,
    WorkflowApprovalResponse,
    WorkflowRecord,
    utc_now,
)
from .orchestration import (
    ToolIntentDispatcher,
    WorkflowCoordinator,
    allowed_tool_names,
    available_tool_names,
)
from .providers import (
    AgentRuntimeProvider,
    AgentRuntimeResult,
    ToolIntentProvider,
    build_default_intent_provider,
)
from .state import AgentServiceStore, build_agent_service_store

_SERVER_ONLY_STATE_KEYS = frozenset(
    {
        "Authorization",
        "accessToken",
        "access_token",
        "allowed_tools",
        "authContextRef",
        "auth_context_ref",
        "authorization",
        "tokenRef",
        "token_ref",
        "token_scopes",
    }
)

_TrustedRequestT = TypeVar("_TrustedRequestT", bound=PlanWorkflowRequest | ThreadCreateRequest)

_AGENT_DESCRIPTORS = (
    AgentDescriptor(
        name="google_adk_coordinator",
        description=(
            "Google ADK coordinator agent that emits assistant narration "
            "and typed tool intents."
        ),
    ),
)


class WorkflowExecutionError(RuntimeError):
    """Raised when an approved workflow cannot complete outbound execution."""


def create_app(
    store: AgentServiceStore | None = None,
    intent_provider: ToolIntentProvider | None = None,
) -> FastAPI:
    state_store = store or build_agent_service_store()
    provider = intent_provider or build_default_intent_provider()
    runtime_provider = provider if isinstance(provider, AgentRuntimeProvider) else None
    coordinator = WorkflowCoordinator(intent_provider=provider)
    dispatcher = ToolIntentDispatcher()
    app = FastAPI(title="Agent Service")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/agents", response_model=AgentListResponse)
    async def list_agents() -> AgentListResponse:
        return AgentListResponse(agents=list(_AGENT_DESCRIPTORS))

    @app.post("/workflows/plan", response_model=PlanWorkflowResponse)
    async def plan_workflow(
        request: PlanWorkflowRequest,
        http_request: Request,
    ) -> PlanWorkflowResponse:
        context = _trusted_context_from_request(http_request)
        request = _request_with_trusted_context(request, context)
        workflow = await _plan_workflow_from_intents(
            state_store=state_store,
            dispatcher=dispatcher,
            request=request,
            result=AgentRuntimeResult(
                assistant_message="",
                tool_intents=await coordinator.propose(request),
            ),
        )
        return PlanWorkflowResponse(workflow=workflow)

    @app.post("/runs/stream")
    async def run_agent(
        request: RunAgentRequest,
        http_request: Request,
    ) -> StreamingResponse:
        if runtime_provider is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Agent Runtime provider is required for streaming runs",
            )
        context = _trusted_context_from_request(http_request)
        trusted_request = _request_with_trusted_context(request, context)

        return StreamingResponse(
            _stream_agent_run(
                state_store=state_store,
                dispatcher=dispatcher,
                runtime_provider=runtime_provider,
                request=trusted_request,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/workflows/{workflow_id}", response_model=PlanWorkflowResponse)
    async def get_workflow(
        workflow_id: str,
        http_request: Request,
    ) -> PlanWorkflowResponse:
        context = _trusted_context_from_request(http_request)
        return PlanWorkflowResponse(
            workflow=await _require_workflow(
                state_store,
                workflow_id=workflow_id,
                user_id=context.user_id,
                session_id=context.session_id,
                tenant_id=context.tenant_id,
            )
        )

    @app.post("/workflows/{workflow_id}/approve", response_model=WorkflowApprovalResponse)
    async def approve_workflow(
        workflow_id: str,
        request: WorkflowApprovalRequest,
        http_request: Request,
    ) -> WorkflowApprovalResponse:
        context = _trusted_context_from_request(http_request)
        record = await _require_workflow(
            state_store,
            workflow_id=workflow_id,
            user_id=context.user_id,
            session_id=context.session_id,
            tenant_id=context.tenant_id,
        )
        if request.plan_hash != record.plan_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="plan_hash does not match workflow manifest",
            )
        if record.status in {"cancelled", "completed", "executing", "failed"}:
            await _save_thread_workflow_state(state_store, record)
            return WorkflowApprovalResponse(
                workflow=record,
                token_exchange={
                    "attempted": False,
                    "reason": f"workflow already {record.status}",
                },
            )
        if not request.approved:
            workflow = await state_store.save_workflow(
                record.model_copy(update={"status": "cancelled"})
            )
            await _save_thread_workflow_state(state_store, workflow)
            return WorkflowApprovalResponse(workflow=workflow)
        if not record.token_ref:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="token_ref is required for OBO token exchange",
            )
        auth_context_ref = await state_store.get_auth_context(
            user_id=record.user_id,
            session_id=record.session_id,
            tenant_id=record.tenant_id,
            token_ref=record.token_ref,
        )
        if auth_context_ref is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="auth context is not registered for token_ref",
            )

        approval = ApprovedWorkflow(
            workflow_id=record.workflow_id,
            approval_id=f"approval-{uuid4().hex}",
            plan_hash=record.plan_hash,
            approved_by_user_id=context.user_id,
            approved_scopes=record.policy.required_scopes,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        exchanging = await state_store.save_workflow(
            record.model_copy(
                update={
                    "status": "executing",
                    "approved_workflow": approval,
                }
            )
        )
        try:
            token_response = await _exchange_obo_token(exchanging, approval, auth_context_ref)
            egress_results = await _execute_approved_steps(exchanging, approval, token_response)
        except Exception as exc:
            await _mark_workflow_failed(state_store, exchanging, exc)
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=_safe_execution_failure_detail(exc),
            ) from exc
        completed = await state_store.save_workflow(
            exchanging.model_copy(
                update={
                    "status": "completed",
                    "egress_results": egress_results,
                }
            )
        )
        await _save_thread_workflow_state(state_store, completed)
        return WorkflowApprovalResponse(
            workflow=completed,
            token_exchange={
                "attempted": True,
                "audience": token_response.audience,
                "scopes": token_response.scopes,
                "expires_at": token_response.expires_at.isoformat(),
            },
        )

    @app.post("/token-context")
    async def register_token_context(
        request: TokenContextRegistrationRequest,
        http_request: Request,
    ) -> dict[str, str]:
        context = _trusted_context_from_request(http_request)
        if request.token_ref != context.token_ref:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="token_ref does not match trusted session context",
            )
        await state_store.register_auth_context(
            TokenRegistryRecord(
                user_id=context.user_id,
                session_id=context.session_id,
                tenant_id=context.tenant_id,
                token_ref=request.token_ref,
                auth_context_ref=request.auth_context_ref,
            )
        )
        return {"token_ref": request.token_ref}

    @app.post("/threads", response_model=ThreadResponse)
    async def create_thread(
        request: ThreadCreateRequest,
        http_request: Request,
    ) -> ThreadResponse:
        context = _trusted_context_from_request(http_request)
        request = _request_with_trusted_context(request, context)
        token_ref = await _register_thread_auth_context(state_store, request)
        thread = ThreadRecord(
            thread_id=request.thread_id or f"thread-{uuid4().hex}",
            user_id=request.user_id,
            session_id=request.session_id,
            tenant_id=request.tenant_id,
            messages=request.messages,
            state=_thread_state_payload(
                _thread_create_state(request),
                user_id=request.user_id,
                session_id=request.session_id,
                tenant_id=request.tenant_id,
                token_ref=token_ref,
                active_workflow_id=None,
            ),
            title=request.title,
            token_ref=token_ref,
        )
        return ThreadResponse(thread=await state_store.save_thread(thread))

    @app.get("/threads/{thread_id}", response_model=ThreadResponse)
    async def restore_thread(
        thread_id: str,
        http_request: Request,
    ) -> ThreadResponse:
        context = _trusted_context_from_request(http_request)
        thread = await state_store.get_thread(
            thread_id=thread_id,
            user_id=context.user_id,
            session_id=context.session_id,
            tenant_id=context.tenant_id,
        )
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")
        return ThreadResponse(thread=thread)

    app.state.agent_service_store = state_store
    return app


def _trusted_context_from_request(request: Request) -> TrustedSessionContext:
    try:
        return verify_session_context(
            encoded_context=request.headers.get(SESSION_CONTEXT_HEADER),
            signature=request.headers.get(SESSION_CONTEXT_SIGNATURE_HEADER),
            secret=_internal_auth_secret(),
        )
    except InternalAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


def _request_with_trusted_context(
    request: _TrustedRequestT,
    context: TrustedSessionContext,
) -> _TrustedRequestT:
    updates: dict[str, object] = {
        "allowed_tools": context.allowed_tools,
        "auth_context_ref": None,
        "session_id": context.session_id,
        "tenant_id": context.tenant_id,
        "token_ref": context.token_ref,
        "token_scopes": context.token_scopes,
        "user_id": context.user_id,
    }
    fields = set(type(request).model_fields)
    return cast(
        _TrustedRequestT,
        request.model_copy(
            update={key: value for key, value in updates.items() if key in fields}
        ),
    )


async def _plan_workflow_from_intents(
    *,
    state_store: AgentServiceStore,
    dispatcher: ToolIntentDispatcher,
    request: PlanWorkflowRequest,
    result: AgentRuntimeResult,
    assistant_message_id: str | None = None,
    assistant_text: str | None = None,
    run_id: str | None = None,
) -> WorkflowRecord:
    session = await state_store.upsert_session(request)
    dispatch = dispatcher.dispatch(request, result.tool_intents)
    workflow_id = _workflow_id(
        request,
        [intent.tool_name for intent in dispatch.tool_intents],
    )
    proposal = WorkflowPlan(
        workflow_id=workflow_id,
        user_id=request.user_id,
        session_id=request.session_id,
        tenant_id=request.tenant_id,
        steps=dispatch.steps,
    )
    workflow = WorkflowRecord(
        workflow_id=workflow_id,
        thread_id=request.thread_id,
        session_id=request.session_id,
        user_id=request.user_id,
        tenant_id=request.tenant_id,
        status="awaiting_approval" if dispatch.policy.requires_hitl else "ready",
        proposal=proposal,
        plan_hash=plan_hash(proposal),
        tool_intents=dispatch.tool_intents,
        policy=dispatch.policy,
        token_ref=session.token_ref,
    )
    workflow = await state_store.save_workflow(workflow)
    if request.thread_id:
        await _save_thread_snapshot_for_workflow(
            state_store=state_store,
            request=request,
            workflow=workflow,
            token_ref=session.token_ref,
            assistant_message_id=assistant_message_id,
            assistant_text=assistant_text,
            run_id=run_id,
        )
    return workflow


async def _stream_agent_run(
    *,
    state_store: AgentServiceStore,
    dispatcher: ToolIntentDispatcher,
    runtime_provider: AgentRuntimeProvider,
    request: RunAgentRequest,
) -> AsyncIterator[str]:
    sensitive_values = _request_sensitive_values(request)
    yield _encode_sse(
        {
            "type": "RUN_STARTED",
            "threadId": request.thread_id,
            "runId": request.run_id,
        }
    )
    message_id = f"{request.run_id}:assistant"
    try:
        async with asyncio.timeout(_agent_runtime_timeout_seconds()):
            result = await runtime_provider.run(
                SanitizedWorkflowContext.from_request(request),
                allowed_tool_names=allowed_tool_names(request.allowed_tools),
                available_tool_names=available_tool_names(),
            )
        result = _redact_runtime_result(result, sensitive_values)
        workflow = await _plan_workflow_from_intents(
            state_store=state_store,
            dispatcher=dispatcher,
            request=request,
            result=result,
            assistant_message_id=message_id,
            assistant_text=result.assistant_message,
            run_id=request.run_id,
        )
        yield _encode_sse(
            {
                "type": "TEXT_MESSAGE_START",
                "messageId": message_id,
                "role": "assistant",
            }
        )
        if result.assistant_message:
            yield _encode_sse(
                {
                    "type": "TEXT_MESSAGE_CONTENT",
                    "messageId": message_id,
                    "delta": result.assistant_message,
                }
            )
        yield _encode_sse({"type": "TEXT_MESSAGE_END", "messageId": message_id})

        workflow_payload = _public_workflow_payload(workflow)
        yield _encode_sse(
            {
                "type": "STATE_DELTA",
                "delta": [{"op": "add", "path": "/workflow", "value": workflow_payload}],
            }
        )

        for index, step in enumerate(workflow.proposal.steps, start=1):
            step_payload = step.model_dump(mode="json")
            tool_args_delta = _redact_sensitive_text(
                step.input_payload_json,
                sensitive_values,
            )
            tool_call_id = f"{request.run_id}:{step.step_id or f'step-{index}'}"
            yield _encode_sse(
                {
                    "type": "TOOL_CALL_START",
                    "toolCallId": tool_call_id,
                    "toolCallName": step.action,
                    "parentMessageId": message_id,
                }
            )
            yield _encode_sse(
                {
                    "type": "TOOL_CALL_ARGS",
                    "toolCallId": tool_call_id,
                    "delta": tool_args_delta,
                }
            )
            yield _encode_sse({"type": "TOOL_CALL_END", "toolCallId": tool_call_id})
            yield _encode_sse(
                {
                    "type": "TOOL_CALL_RESULT",
                    "messageId": message_id,
                    "toolCallId": tool_call_id,
                    "content": _json_string(
                        {
                            "status": "planned",
                            "step": {
                                "step_id": step_payload.get("step_id"),
                                "target_agent": step_payload.get("target_agent"),
                                "action": step_payload.get("action"),
                            },
                        }
                    ),
                    "role": "tool",
                }
            )

        approval_event = _approval_event_payload(workflow)
        if approval_event is not None:
            yield _encode_sse(
                {
                    "type": "CUSTOM",
                    "name": "hitl.approval.requested",
                    "value": approval_event,
                }
            )

        yield _encode_sse(
            {
                "type": "RUN_FINISHED",
                "threadId": request.thread_id,
                "runId": request.run_id,
            }
        )
    except Exception as exc:
        yield _encode_sse(
            {
                "type": "RUN_ERROR",
                "message": _redact_sensitive_text(
                    str(exc) or exc.__class__.__name__,
                    sensitive_values,
                ),
                "code": "AGENT_RUNTIME_ERROR",
            }
        )


def _encode_sse(data: dict[str, Any]) -> str:
    return f"data: {_json_string(data)}\n\n"


def _json_string(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _request_sensitive_values(request: PlanWorkflowRequest) -> frozenset[str]:
    return frozenset(
        value
        for value in (request.auth_context_ref, request.token_ref)
        if isinstance(value, str) and value
    )


def _redact_runtime_result(
    result: AgentRuntimeResult,
    sensitive_values: frozenset[str],
) -> AgentRuntimeResult:
    if not sensitive_values:
        return result
    return AgentRuntimeResult(
        assistant_message=_redact_sensitive_text(result.assistant_message, sensitive_values),
        tool_intents=[
            _redact_tool_intent(intent, sensitive_values) for intent in result.tool_intents
        ],
    )


def _redact_tool_intent(
    intent: ToolIntent,
    sensitive_values: frozenset[str],
) -> ToolIntent:
    arguments = _redact_sensitive_value(intent.arguments, sensitive_values)
    return intent.model_copy(
        update={
            "arguments": arguments if isinstance(arguments, dict) else {},
            "metadata_ref": _redact_sensitive_text(intent.metadata_ref, sensitive_values),
            "reason": (
                None
                if intent.reason is None
                else _redact_sensitive_text(intent.reason, sensitive_values)
            ),
        }
    )


def _redact_sensitive_value(value: object, sensitive_values: frozenset[str]) -> object:
    if isinstance(value, str):
        return _redact_sensitive_text(value, sensitive_values)
    if isinstance(value, list):
        return [
            _redact_sensitive_value(item, sensitive_values)
            for item in cast(list[object], value)
        ]
    if isinstance(value, dict):
        return {
            key: _redact_sensitive_value(item, sensitive_values)
            for key, item in cast(dict[str, object], value).items()
            if key not in _BROWSER_PRIVATE_KEYS
        }
    return value


def _redact_sensitive_text(value: str, sensitive_values: frozenset[str]) -> str:
    redacted = value
    for sensitive_value in sensitive_values:
        redacted = redacted.replace(sensitive_value, "[REDACTED]")
    return redacted


_BROWSER_PRIVATE_KEYS = {
    "access_token",
    "authContextRef",
    "auth_context_ref",
    "authorization",
    "id_token",
    "oboTokenRef",
    "obo_token_ref",
    "refresh_token",
    "session_id",
    "tenant_id",
    "tokenRef",
    "token_ref",
    "user_id",
}


def _public_workflow_payload(workflow: WorkflowRecord) -> dict[str, object]:
    payload = workflow.model_dump(mode="json")
    public = _strip_browser_private_keys(payload)
    return cast(dict[str, object], public)


def _strip_browser_private_keys(value: object) -> object:
    if isinstance(value, list):
        return [_strip_browser_private_keys(item) for item in cast(list[object], value)]
    if isinstance(value, dict):
        return {
            key: _strip_browser_private_keys(item)
            for key, item in cast(dict[str, object], value).items()
            if key not in _BROWSER_PRIVATE_KEYS
        }
    return value


def _approval_event_payload(workflow: WorkflowRecord) -> dict[str, Any] | None:
    if workflow.status != "awaiting_approval":
        return None
    return {
        "kind": "HITL_APPROVAL",
        "workflow_id": workflow.workflow_id,
        "plan_hash": workflow.plan_hash,
        "required_scopes": workflow.policy.required_scopes,
        "message": workflow.policy.human_description,
    }


async def _require_workflow(
    state_store: AgentServiceStore,
    *,
    workflow_id: str,
    user_id: str,
    session_id: str,
    tenant_id: str | None,
) -> WorkflowRecord:
    record = await state_store.get_workflow(
        workflow_id=workflow_id,
        user_id=user_id,
        session_id=session_id,
        tenant_id=tenant_id,
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found")
    return record


async def _register_thread_auth_context(
    state_store: AgentServiceStore,
    request: ThreadCreateRequest,
) -> str | None:
    token_ref = request.token_ref
    if request.auth_context_ref and token_ref:
        await state_store.register_auth_context(
            TokenRegistryRecord(
                user_id=request.user_id,
                session_id=request.session_id,
                tenant_id=request.tenant_id,
                token_ref=token_ref,
                auth_context_ref=request.auth_context_ref,
            )
        )
    return token_ref


async def _save_thread_snapshot_for_workflow(
    *,
    state_store: AgentServiceStore,
    request: PlanWorkflowRequest,
    workflow: WorkflowRecord,
    token_ref: str | None,
    assistant_message_id: str | None = None,
    assistant_text: str | None = None,
    run_id: str | None = None,
) -> None:
    if request.thread_id is None:
        return
    existing = await state_store.get_thread(
        thread_id=request.thread_id,
        user_id=request.user_id,
        session_id=request.session_id,
        tenant_id=request.tenant_id,
    )
    state_payload = _thread_state_payload(
        request.state,
        user_id=request.user_id,
        session_id=request.session_id,
        tenant_id=request.tenant_id,
        token_ref=token_ref,
        active_workflow_id=workflow.workflow_id,
    )
    state_payload["workflow"] = _public_workflow_payload(workflow)
    await state_store.save_thread(
        ThreadRecord(
            thread_id=request.thread_id,
            user_id=request.user_id,
            session_id=request.session_id,
            tenant_id=request.tenant_id,
            messages=_restorable_thread_messages(
                request.messages or ([] if existing is None else existing.messages),
                assistant_message=_assistant_thread_message(
                    workflow=workflow,
                    message_id=assistant_message_id,
                    text=assistant_text,
                    run_id=run_id,
                ),
            ),
            state=state_payload,
            token_ref=token_ref,
            active_workflow_id=workflow.workflow_id,
            created_at=utc_now() if existing is None else existing.created_at,
            updated_at=utc_now(),
        )
    )


async def _save_thread_workflow_state(
    state_store: AgentServiceStore,
    workflow: WorkflowRecord,
) -> None:
    if workflow.thread_id is None:
        return
    existing = await state_store.get_thread(
        thread_id=workflow.thread_id,
        user_id=workflow.user_id,
        session_id=workflow.session_id,
        tenant_id=workflow.tenant_id,
    )
    if existing is None:
        return

    state_payload = dict(existing.state)
    state_payload["workflow"] = _public_workflow_payload(workflow)
    state_payload["active_workflow_id"] = workflow.workflow_id
    await state_store.save_thread(
        existing.model_copy(
            update={
                "active_workflow_id": workflow.workflow_id,
                "state": state_payload,
                "updated_at": utc_now(),
            }
        )
    )


async def _mark_workflow_failed(
    state_store: AgentServiceStore,
    workflow: WorkflowRecord,
    exc: Exception,
) -> WorkflowRecord:
    failed = await state_store.save_workflow(
        workflow.model_copy(
            update={
                "status": "failed",
                "egress_results": [
                    {
                        "error_type": exc.__class__.__name__,
                        "message": _safe_execution_failure_detail(exc),
                        "status": "failed",
                    }
                ],
            }
        )
    )
    await _save_thread_workflow_state(state_store, failed)
    return failed


def _safe_execution_failure_detail(exc: Exception) -> str:
    if isinstance(exc, WorkflowExecutionError):
        return str(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        return f"workflow execution failed with HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.HTTPError):
        return f"workflow execution transport failed: {exc.__class__.__name__}"
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return f"workflow execution failed: {exc.__class__.__name__}"


def _restorable_thread_messages(
    messages: list[dict[str, Any]],
    *,
    assistant_message: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    restorable: list[dict[str, Any]] = []
    for message in messages:
        normalized = _normalize_thread_message(message, restorable)
        if normalized is not None:
            restorable.append(normalized)

    if assistant_message is not None:
        restorable = [
            message
            for message in restorable
            if message.get("id") != assistant_message.get("id")
        ]
        restorable.append(assistant_message)
    return restorable


def _normalize_thread_message(
    message: dict[str, Any],
    previous_messages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    role = message.get("role")
    if role == "tool":
        _merge_tool_result(message, previous_messages)
        return None
    if role == "assistant":
        return _normalize_assistant_message(message)
    if role in {"system", "user"}:
        return _normalize_basic_message(message, cast(str, role))
    return None


def _normalize_basic_message(message: dict[str, Any], role: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "id": _message_id(message, f"{role}-{uuid4().hex}"),
        "role": role,
        "content": _restorable_message_content(message.get("content")),
    }
    name = message.get("name")
    if isinstance(name, str) and name:
        normalized["name"] = name
    return normalized


def _normalize_assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    parts = _assistant_content_parts(message.get("content"))
    seen_tool_call_ids = {
        part.get("toolCallId")
        for part in parts
        if part.get("type") == "tool-call"
    }
    for tool_call in _tool_calls_from_message(message):
        tool_call_id = tool_call.get("toolCallId")
        if tool_call_id in seen_tool_call_ids:
            continue
        parts.append(tool_call)
        seen_tool_call_ids.add(tool_call_id)

    normalized: dict[str, Any] = {
        "id": _message_id(message, f"assistant-{uuid4().hex}"),
        "role": "assistant",
        "content": parts,
    }
    name = message.get("name")
    if isinstance(name, str) and name:
        normalized["name"] = name
    return normalized


def _assistant_content_parts(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    if not isinstance(content, list):
        return []

    parts: list[dict[str, Any]] = []
    content_items = cast(list[Any], content)  # type: ignore[redundant-cast]
    for part in content_items:
        if not isinstance(part, dict):
            continue
        safe_part = _sanitize_message_payload(cast(dict[str, Any], part))
        part_type = safe_part.get("type")
        if part_type == "text" and isinstance(safe_part.get("text"), str):
            parts.append(safe_part)
        elif part_type == "tool-call":
            parts.append(_normalize_tool_call_part(safe_part))
        elif isinstance(part_type, str) and part_type in {
            "data",
            "file",
            "image",
            "reasoning",
            "source",
        }:
            parts.append(safe_part)
    return parts


def _restorable_message_content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return _sanitize_message_payload(content)
    return ""


def _tool_calls_from_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    raw_tool_calls_value = message.get("toolCalls")
    if not isinstance(raw_tool_calls_value, list):
        raw_tool_calls_value = message.get("tool_calls")
    if not isinstance(raw_tool_calls_value, list):
        return []

    parts: list[dict[str, Any]] = []
    raw_tool_call_items = cast(list[Any], raw_tool_calls_value)  # type: ignore[redundant-cast]
    for raw_tool_call in raw_tool_call_items:
        if not isinstance(raw_tool_call, dict):
            continue
        tool_call = cast(dict[str, Any], raw_tool_call)
        function = tool_call.get("function")
        function_payload: dict[str, Any] = (
            cast(dict[str, Any], function) if isinstance(function, dict) else {}
        )
        tool_name = (
            _string_message_value(function_payload, "name")
            or _string_message_value(tool_call, "toolName", "tool_name", "name")
            or "tool"
        )
        args_text = (
            _string_message_value(function_payload, "arguments")
            or _string_message_value(tool_call, "argsText", "args_text", "arguments")
            or "{}"
        )
        parts.append(
            _normalize_tool_call_part(
                {
                    "type": "tool-call",
                    "toolCallId": _string_message_value(tool_call, "id", "toolCallId")
                    or f"tool-{uuid4().hex}",
                    "toolName": tool_name,
                    "argsText": args_text,
                }
            )
        )
    return parts


def _normalize_tool_call_part(part: dict[str, Any]) -> dict[str, Any]:
    tool_call_id = (
        _string_message_value(part, "toolCallId", "tool_call_id") or f"tool-{uuid4().hex}"
    )
    args_text = _string_message_value(part, "argsText", "args_text")
    args = part.get("args")
    if not isinstance(args, dict):
        args = _parse_json_object(args_text)
    if args_text is None:
        args_text = _json_string(args or {})

    normalized: dict[str, Any] = {
        "type": "tool-call",
        "toolCallId": tool_call_id,
        "toolName": _string_message_value(part, "toolName", "tool_name", "name") or "tool",
        "args": _sanitize_message_payload(args or {}),
        "argsText": args_text,
    }
    if "result" in part:
        normalized["result"] = _sanitize_message_payload(part["result"])
    if isinstance(part.get("isError"), bool):
        normalized["isError"] = part["isError"]
    return normalized


def _merge_tool_result(
    tool_message: dict[str, Any],
    previous_messages: list[dict[str, Any]],
) -> None:
    tool_call_id = _string_message_value(tool_message, "toolCallId", "tool_call_id")
    if not tool_call_id:
        return
    for message in reversed(previous_messages):
        if message.get("role") != "assistant" or not isinstance(message.get("content"), list):
            continue
        for part in reversed(cast(list[Any], message["content"])):
            if not isinstance(part, dict):
                continue
            tool_part = cast(dict[str, Any], part)
            if tool_part.get("type") != "tool-call" or tool_part.get("toolCallId") != tool_call_id:
                continue
            content = tool_message.get("content")
            result = _parse_json_value(content) if isinstance(content, str) else content
            tool_part["result"] = _sanitize_message_payload(result)
            if "error" in tool_message or tool_message.get("status") == "error":
                tool_part["isError"] = True
            return


def _assistant_thread_message(
    *,
    workflow: WorkflowRecord,
    message_id: str | None,
    text: str | None,
    run_id: str | None,
) -> dict[str, Any] | None:
    parts: list[dict[str, Any]] = []
    if text:
        parts.append({"type": "text", "text": text})

    for index, step in enumerate(workflow.proposal.steps, start=1):
        tool_call_id = (
            f"{run_id}:{step.step_id or f'step-{index}'}"
            if run_id
            else f"tool-{uuid4().hex}"
        )
        args = _parse_json_object(step.input_payload_json)
        parts.append(
            {
                "type": "tool-call",
                "toolCallId": tool_call_id,
                "toolName": step.action,
                "args": _sanitize_message_payload(args),
                "argsText": step.input_payload_json,
                "result": {
                    "status": "planned",
                    "step": {
                        "step_id": step.step_id,
                        "target_agent": step.target_agent,
                        "action": step.action,
                    },
                },
            }
        )

    if not parts:
        return None
    return {
        "id": message_id or f"assistant-{uuid4().hex}",
        "role": "assistant",
        "content": parts,
    }


def _message_id(message: dict[str, Any], fallback: str) -> str:
    value = message.get("id")
    return value if isinstance(value, str) and value else fallback


def _string_message_value(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _parse_json_object(value: str | None) -> dict[str, Any]:
    parsed: Any = _parse_json_value(value) if value is not None else {}
    return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}


def _parse_json_value(value: str | None) -> Any:
    if value is None or not value:
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _sanitize_message_payload(value: Any) -> Any:
    return _strip_server_only_state(value)


def _thread_state_payload(
    state: dict[str, Any],
    *,
    user_id: str,
    session_id: str,
    tenant_id: str | None,
    token_ref: str | None,
    active_workflow_id: str | None,
) -> dict[str, Any]:
    payload = _sanitize_ag_ui_state(state)
    payload["user_id"] = user_id
    payload["session_id"] = session_id
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    if token_ref is not None:
        payload["token_ref"] = token_ref
    if active_workflow_id is not None:
        payload["active_workflow_id"] = active_workflow_id
    return payload


def _thread_create_state(request: ThreadCreateRequest) -> dict[str, Any]:
    state = dict(request.state)
    if request.allowed_tools is not None:
        state["allowed_tools"] = request.allowed_tools
    if request.token_scopes:
        state["token_scopes"] = request.token_scopes
    return state


def _sanitize_ag_ui_state(state: dict[str, Any]) -> dict[str, Any]:
    sanitized = _strip_server_only_state(state)
    return cast(dict[str, Any], sanitized) if isinstance(sanitized, dict) else {}


def _strip_server_only_state(value: object) -> object:
    if isinstance(value, dict):
        payload = cast(dict[str, Any], value)
        return {
            key: _strip_server_only_state(item)
            for key, item in payload.items()
            if key not in _SERVER_ONLY_STATE_KEYS
        }
    if isinstance(value, list):
        items = cast(list[object], value)
        return [_strip_server_only_state(item) for item in items]
    return value


def _workflow_id(request: PlanWorkflowRequest, tool_names: list[str]) -> str:
    material = json.dumps(
        {
            "query": request.query,
            "session_id": request.session_id,
            "tenant_id": request.tenant_id,
            "tool_names": tool_names,
            "user_id": request.user_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"wf-{sha256(material.encode()).hexdigest()[:16]}"


def _obo_config(audience: str | None) -> Auth0OnBehalfOfConfig:
    domain = _required_env("AUTH0_DOMAIN")
    return Auth0OnBehalfOfConfig(
        domain=domain,
        token_endpoint=f"https://{domain.removeprefix('https://').removeprefix('http://').rstrip('/')}/oauth/token",
        client_id=_required_env("AUTH0_OBO_CLIENT_ID"),
        client_secret=SecretStr(_required_env("AUTH0_OBO_CLIENT_SECRET")),
        audience=audience or _required_env("AUTH0_OBO_AUDIENCE"),
    )


async def _exchange_obo_token(
    record: WorkflowRecord,
    approval: ApprovedWorkflow,
    auth_context_ref: str,
) -> WorkflowTokenExchangeResponse:
    requested_audience = _requested_audience(record)
    request = WorkflowTokenExchangeRequest(
        user_id=record.user_id,
        session_id=record.session_id,
        workflow_id=record.workflow_id,
        approval_id=approval.approval_id,
        plan_hash=record.plan_hash,
        tenant_id=record.proposal.tenant_id,
        auth_context_ref=auth_context_ref,
        requested_scopes=_obo_requested_scopes(record),
        requested_audience=requested_audience,
        ttl_seconds=900,
    )
    async with Auth0OnBehalfOfClient(timeout=float(os.getenv("AUTH0_OBO_TIMEOUT", "10"))) as client:
        return await client.exchange_for_workflow_token(_obo_config(requested_audience), request)


def _requested_audience(record: WorkflowRecord) -> str:
    audiences = {
        step.downstream_audience
        for step in record.proposal.steps
        if step.downstream_audience
    }
    if len(audiences) == 1:
        audience_name = next(iter(audiences))
        mapped = os.getenv(f"{audience_name.upper().replace('-', '_')}_AUDIENCE")
        if mapped:
            return mapped
    return os.getenv("AUTH0_OBO_DOWNSTREAM_AUDIENCE") or _required_env("AUTH0_OBO_AUDIENCE")


def _obo_requested_scopes(record: WorkflowRecord) -> list[str]:
    scopes = set(record.policy.required_scopes)
    for intent in record.tool_intents:
        spec = get_tool_authorization(intent.tool_name)
        scopes.update(spec.auth0_scope_candidates)
    return sorted(scopes)


async def _execute_approved_steps(
    record: WorkflowRecord,
    approval: ApprovedWorkflow,
    token_response: WorkflowTokenExchangeResponse,
) -> list[dict[str, object]]:
    if not token_response.audience:
        raise WorkflowExecutionError("obo token audience is required")
    egress_url = os.getenv("EGRESS_GATEWAY_URL", "http://egress-gateway:8091").rstrip("/")
    results: list[dict[str, object]] = []
    async with httpx.AsyncClient(base_url=egress_url, timeout=20.0) as client:
        for step in record.proposal.steps:
            if approval.expires_at is not None and approval.expires_at <= datetime.now(UTC):
                raise WorkflowExecutionError("approval_expired")
            primitive: Literal["DISCOVERY", "READ", "EXECUTE", "MUTATION"] = (
                "READ" if step.operation_type == "READ" else "EXECUTE"
            )
            method: Literal["GET", "POST"] = "GET" if step.operation_type == "READ" else "POST"
            target_mcp = step.downstream_audience
            if not target_mcp:
                raise WorkflowExecutionError(
                    f"workflow step {step.step_id} is missing a downstream MCP target"
                )
            arguments = json.loads(step.input_payload_json)
            grant = ExecutionGrant(
                workflow_id=record.workflow_id,
                approval_id=approval.approval_id,
                plan_hash=record.plan_hash,
                step_id=step.step_id,
                primitive=primitive,
                method=method,
                target_mcp=target_mcp,
                tool_name=step.action,
                arguments=arguments,
                required_scopes=step.required_scopes,
                audience=token_response.audience,
                user_id=record.user_id,
                session_id=record.session_id,
                tenant_id=record.tenant_id,
                approved_by_user_id=approval.approved_by_user_id,
                expires_at=approval.expires_at,
                correlation_id=f"{record.workflow_id}:{step.step_id}",
            )
            response = await client.post(
                "/egress/mcp",
                headers=signed_session_context_headers(
                    _egress_trusted_context(record, approval),
                    secret=_internal_auth_secret(),
                ),
                json={
                    "primitive": primitive,
                    "method": method,
                    "target_mcp": target_mcp,
                    "tool_name": step.action,
                    "arguments": arguments,
                    "workflow_id": record.workflow_id,
                    "approval_id": approval.approval_id,
                    "obo_token_ref": f"obo:{approval.approval_id}",
                    "access_token": token_response.access_token,
                    "execution_grant": grant.model_dump(mode="json"),
                    "execution_grant_signature": sign_execution_grant(
                        grant,
                        secret=_internal_auth_secret(),
                    ),
                    "token_audience": token_response.audience,
                    "token_scopes": token_response.scopes,
                },
            )
            response.raise_for_status()
            result = cast(dict[str, object], response.json())
            if _egress_result_failed(result):
                raise WorkflowExecutionError("egress gateway reported failed MCP execution")
            public_result = _strip_browser_private_keys(result)
            results.append(cast(dict[str, object], public_result))
    return results


def _egress_result_failed(result: dict[str, object]) -> bool:
    outbound = result.get("outbound")
    if not isinstance(outbound, dict):
        return False
    outbound_payload = cast(dict[str, object], outbound)
    mcp_result = outbound_payload.get("mcp_result")
    if not isinstance(mcp_result, dict):
        return True
    mcp_payload = cast(dict[str, object], mcp_result)
    return mcp_payload.get("status") == "failed" or mcp_payload.get("is_error") is True


def _egress_trusted_context(
    record: WorkflowRecord,
    approval: ApprovedWorkflow,
) -> TrustedSessionContext:
    return TrustedSessionContext(
        allowed_tools=None,
        correlation_id=approval.approval_id,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        session_id=record.session_id,
        tenant_id=record.tenant_id,
        token_ref=record.token_ref,
        token_scopes=record.policy.required_scopes,
        user_id=record.user_id,
    )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{name} is required for OBO token exchange",
        )
    return value.strip()


def _agent_runtime_timeout_seconds() -> float:
    value = os.getenv("AGENT_RUNTIME_TIMEOUT_SECONDS")
    if not value or not value.strip():
        return 25.0
    return float(value)


def _internal_auth_secret() -> str:
    return os.getenv("INTERNAL_SERVICE_AUTH_SECRET") or ""


app = create_app()

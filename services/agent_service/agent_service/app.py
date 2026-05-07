from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal, cast
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, status
from pydantic import SecretStr
from token_broker import (
    Auth0OnBehalfOfClient,
    Auth0OnBehalfOfConfig,
    WorkflowTokenExchangeRequest,
    WorkflowTokenExchangeResponse,
)
from workflow_core import (
    ApprovedWorkflow,
    ToolIntent,
    ToolProposal,
    WorkflowPlan,
    WorkflowStep,
    evaluate_workflow_policy,
    get_tool_authorization,
    materialize_scopes_for_proposal,
    plan_hash,
    scope_requirements_for_auth0_token,
    scope_requirements_for_tool,
)

from .agents import AGENTS, default_read_intent
from .models import (
    AgentDescriptor,
    AgentListResponse,
    PlanWorkflowRequest,
    PlanWorkflowResponse,
    WorkflowApprovalRequest,
    WorkflowApprovalResponse,
    WorkflowRecord,
)
from .state import InMemoryStateStore


def create_app(store: InMemoryStateStore | None = None) -> FastAPI:
    state_store = store or InMemoryStateStore()
    app = FastAPI(title="Agent Service")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/agents", response_model=AgentListResponse)
    async def list_agents() -> AgentListResponse:
        return AgentListResponse(
            agents=[
                AgentDescriptor(name=agent.name, description=agent.description)
                for agent in AGENTS
            ]
        )

    @app.post("/workflows/plan", response_model=PlanWorkflowResponse)
    async def plan_workflow(request: PlanWorkflowRequest) -> PlanWorkflowResponse:
        state_store.upsert_session(request)
        tool_intents = _dedupe_intents(
            [proposal for agent in AGENTS for proposal in agent.propose(request)]
        )
        if request.allowed_tools is not None:
            allowed = set(request.allowed_tools).union({"inspect_request"})
            tool_intents = [intent for intent in tool_intents if intent.tool_name in allowed]
        if not tool_intents:
            tool_intents = [default_read_intent(request)]

        workflow_id = _workflow_id(request, [intent.tool_name for intent in tool_intents])
        steps = [
            _step_from_intent(index, intent, request.token_scopes)
            for index, intent in enumerate(tool_intents, start=1)
        ]
        proposal = WorkflowPlan(
            workflow_id=workflow_id,
            user_id=request.user_id,
            session_id=request.session_id,
            tenant_id=request.tenant_id,
            steps=steps,
        )
        policy = evaluate_workflow_policy(steps)
        workflow = state_store.save_workflow(
            WorkflowRecord(
                workflow_id=workflow_id,
                session_id=request.session_id,
                user_id=request.user_id,
                status="awaiting_approval" if policy.requires_hitl else "ready",
                proposal=proposal,
                plan_hash=plan_hash(proposal),
                tool_intents=tool_intents,
                policy=policy,
                auth_context_ref=request.auth_context_ref,
            )
        )
        return PlanWorkflowResponse(workflow=workflow)

    @app.post("/workflows/{workflow_id}/approve", response_model=WorkflowApprovalResponse)
    async def approve_workflow(
        workflow_id: str,
        request: WorkflowApprovalRequest,
    ) -> WorkflowApprovalResponse:
        record = state_store.get_workflow(workflow_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found")
        if request.plan_hash != record.plan_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="plan_hash does not match workflow manifest",
            )
        if not request.approved:
            workflow = state_store.save_workflow(record.model_copy(update={"status": "cancelled"}))
            return WorkflowApprovalResponse(workflow=workflow)
        if not record.auth_context_ref:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="auth_context_ref is required for OBO token exchange",
            )

        approval = ApprovedWorkflow(
            workflow_id=record.workflow_id,
            approval_id=f"approval-{uuid4().hex}",
            plan_hash=record.plan_hash,
            approved_by_user_id=request.approved_by_user_id,
            approved_scopes=record.policy.required_scopes,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        exchanging = state_store.save_workflow(
            record.model_copy(
                update={
                    "status": "executing",
                    "approved_workflow": approval,
                }
            )
        )
        token_response = await _exchange_obo_token(exchanging, approval)
        egress_results = await _execute_approved_steps(
            exchanging,
            approval,
            token_response.access_token,
        )
        completed = state_store.save_workflow(
            exchanging.model_copy(
                update={
                    "status": "completed",
                    "egress_results": egress_results,
                }
            )
        )
        return WorkflowApprovalResponse(
            workflow=completed,
            token_exchange={
                "attempted": True,
                "audience": token_response.audience,
                "scopes": token_response.scopes,
                "expires_at": token_response.expires_at.isoformat(),
            },
        )

    app.state.agent_service_store = state_store
    return app


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


def _dedupe_intents(tool_intents: list[ToolIntent]) -> list[ToolIntent]:
    deduped: list[ToolIntent] = []
    seen: set[str] = set()
    for intent in tool_intents:
        material = json.dumps(
            {
                "arguments": intent.arguments,
                "mcp_server": intent.mcp_server,
                "tool_name": intent.tool_name,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        if material in seen:
            continue
        seen.add(material)
        deduped.append(intent)
    return deduped


def _step_from_intent(index: int, intent: ToolIntent, token_scopes: list[str]) -> WorkflowStep:
    spec = get_tool_authorization(intent.tool_name)
    proposal = ToolProposal(
        agent_name=intent.agent_name,
        tool_name=intent.tool_name,
        arguments=intent.arguments,
        reason=intent.reason,
    )
    required_scopes = materialize_scopes_for_proposal(
        proposal,
        (
            scope_requirements_for_auth0_token(intent.tool_name, token_scopes)
            if token_scopes
            else scope_requirements_for_tool(intent.tool_name)
        ),
    )
    return WorkflowStep(
        step_id=f"step-{index}",
        target_agent=intent.agent_name,
        action=intent.tool_name,
        input_model_type=f"{intent.tool_name}.arguments",
        input_payload_json=json.dumps(intent.arguments, sort_keys=True, separators=(",", ":")),
        required_scopes=required_scopes,
        downstream_audience=spec.downstream_audience,
        operation_type=cast(Literal["READ", "WRITE", "ADMIN"], spec.op),
        blast_radius=spec.blast_radius,
        hitl_description=spec.hitl_description,
        mutates_external_state=spec.op in {"WRITE", "ADMIN"},
    )


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
) -> WorkflowTokenExchangeResponse:
    requested_audience = _requested_audience(record)
    request = WorkflowTokenExchangeRequest(
        user_id=record.user_id,
        session_id=record.session_id,
        workflow_id=record.workflow_id,
        approval_id=approval.approval_id,
        plan_hash=record.plan_hash,
        tenant_id=record.proposal.tenant_id,
        auth_context_ref=cast(str, record.auth_context_ref),
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
    access_token: str,
) -> list[dict[str, object]]:
    egress_url = os.getenv("EGRESS_GATEWAY_URL", "http://egress-gateway:8091").rstrip("/")
    results: list[dict[str, object]] = []
    async with httpx.AsyncClient(base_url=egress_url, timeout=20.0) as client:
        for step in record.proposal.steps:
            response = await client.post(
                "/egress/mcp",
                json={
                    "primitive": "READ" if step.operation_type == "READ" else "EXECUTE",
                    "method": "GET" if step.operation_type == "READ" else "POST",
                    "target_mcp": step.downstream_audience,
                    "tool_name": step.action,
                    "arguments": json.loads(step.input_payload_json),
                    "workflow_id": record.workflow_id,
                    "approval_id": approval.approval_id,
                    "obo_token_ref": f"obo:{approval.approval_id}",
                    "access_token": access_token,
                },
            )
            response.raise_for_status()
            results.append(cast(dict[str, object], response.json()))
    return results


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{name} is required for OBO token exchange",
        )
    return value.strip()


app = create_app()

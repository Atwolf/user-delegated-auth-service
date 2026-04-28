from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any, cast
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from observability.models import WorkflowEvent
from observability.sidecar_client import ObservabilitySidecarClient
from pydantic import SecretStr
from token_broker import Auth0ClientCredentialsClient, Auth0ClientCredentialsConfig
from workflow_core import (
    ApprovedWorkflow,
    AuthorizationBundle,
    ScopeMaterializationError,
    ScopeRequirement,
    ToolProposal,
    WorkflowPlan,
    WorkflowStatus,
    WorkflowStep,
    materialize_scopes_for_proposal,
    plan_hash,
)

from agent_service_supervisor.config import SupervisorSettings
from agent_service_supervisor.discovery_sqlite import (
    SubagentDiscoveryService,
    SubagentRecord,
)
from agent_service_supervisor.workflow_api_models import (
    Auth0ClientCredentialsTokenRequest,
    Auth0ClientCredentialsTokenResult,
    WorkflowApprovalRequest,
    WorkflowPlanRequest,
    WorkflowRecord,
    WorkflowStepExecutionResult,
    WorkflowTimelineEvent,
)
from agent_service_supervisor.workflow_orchestrator import WorkflowOrchestrator

router = APIRouter()
WorkflowStore = dict[str, WorkflowRecord]


def get_discovery_service(request: Request) -> SubagentDiscoveryService:
    return cast(SubagentDiscoveryService, request.app.state.subagent_discovery)


def get_settings(request: Request) -> SupervisorSettings:
    return cast(SupervisorSettings, request.app.state.settings)


def get_workflow_orchestrator(request: Request) -> WorkflowOrchestrator:
    return cast(WorkflowOrchestrator, request.app.state.workflow_orchestrator)


def get_workflow_store(request: Request) -> WorkflowStore:
    return cast(WorkflowStore, request.app.state.workflow_store)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/subagents", response_model=list[SubagentRecord])
async def list_subagents(
    request: Request,
    discovery: Annotated[SubagentDiscoveryService, Depends(get_discovery_service)],
) -> list[SubagentRecord]:
    cached = getattr(request.app.state, "enabled_subagents", None)
    if cached is not None:
        return cast(list[SubagentRecord], cached)

    records = await discovery.load_enabled_subagents()
    request.app.state.enabled_subagents = records
    return records


@router.post("/subagents/refresh", response_model=list[SubagentRecord])
async def refresh_subagents(
    request: Request,
    discovery: Annotated[SubagentDiscoveryService, Depends(get_discovery_service)],
) -> list[SubagentRecord]:
    records = await discovery.refresh_enabled_subagents()
    request.app.state.enabled_subagents = records
    return records


@router.post(
    "/identity/client-credentials/token",
    response_model=Auth0ClientCredentialsTokenResult,
)
async def exchange_client_credentials_token(
    request: Auth0ClientCredentialsTokenRequest,
    settings: Annotated[SupervisorSettings, Depends(get_settings)],
) -> Auth0ClientCredentialsTokenResult:
    await _emit_sidecar_event(
        settings=settings,
        event_type="frontend.auth0_config_submitted",
        user_id=request.user_id,
        session_id=request.session_id,
        attributes={
            "domain": request.domain,
            "token_endpoint": request.token_endpoint,
            "jwks_endpoint": request.jwks_endpoint,
            "client_id": request.client_id,
            "scope": request.scope,
            "audience": request.audience,
        },
    )

    secret = request.client_secret or (
        SecretStr(settings.auth0_client_secret) if settings.auth0_client_secret else None
    )
    if secret is None:
        raise HTTPException(status_code=400, detail="client_secret is required")

    config = Auth0ClientCredentialsConfig(
        domain=request.domain,
        token_endpoint=request.token_endpoint,
        jwks_endpoint=request.jwks_endpoint,
        client_id=request.client_id,
        client_secret=secret,
        scopes=tuple(request.scope.split()) if request.scope else (),
        audience=request.audience,
    )

    async with Auth0ClientCredentialsClient() as auth0:
        try:
            token = await auth0.exchange(config)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail="Auth0 token exchange failed",
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="Auth0 token exchange failed") from exc

    await _emit_sidecar_event(
        settings=settings,
        event_type="identity.client_credentials_token_exchanged",
        user_id=request.user_id,
        session_id=request.session_id,
        attributes={
            "domain": config.domain,
            "client_id": config.client_id,
            "scopes": list(token.scopes),
            "audience": token.audience,
            "token_ref": token.token_ref,
        },
    )

    return Auth0ClientCredentialsTokenResult(
        access_token=token.access_token,
        expires_in=token.expires_in,
        scope=" ".join(token.scopes),
        audience=token.audience,
        token_ref=token.token_ref,
    )


@router.post("/workflows/plan", response_model=WorkflowRecord)
async def plan_workflow(
    request: WorkflowPlanRequest,
    settings: Annotated[SupervisorSettings, Depends(get_settings)],
    discovery: Annotated[SubagentDiscoveryService, Depends(get_discovery_service)],
    orchestrator: Annotated[WorkflowOrchestrator, Depends(get_workflow_orchestrator)],
    store: Annotated[WorkflowStore, Depends(get_workflow_store)],
) -> WorkflowRecord:
    workflow_id = f"wf-{uuid4().hex}"
    subagents = await discovery.load_enabled_subagents()
    proposals = [
        ToolProposal.model_validate(proposal)
        for proposal in await orchestrator.request_tool_proposals(
            user_query=request.question,
            user_id=request.user_id,
            session_id=request.session_id,
            subagents=subagents,
        )
    ]
    steps = [_step_from_proposal(index, proposal) for index, proposal in enumerate(proposals, 1)]
    plan = WorkflowPlan(
        workflow_id=workflow_id,
        user_id=request.user_id,
        session_id=request.session_id,
        tenant_id=request.tenant_id,
        steps=steps,
    )
    hashed_plan = plan_hash(plan)
    authorization = orchestrator.build_authorization_bundle(
        workflow_id=workflow_id,
        proposals=proposals,
        scopes=[scope for step in steps for scope in step.required_scopes],
    )
    record = WorkflowRecord(
        workflow_id=workflow_id,
        status=WorkflowStatus(status="awaiting_approval"),
        plan=plan,
        plan_hash=hashed_plan,
        authorization=AuthorizationBundle.model_validate(authorization),
        events=[
            WorkflowTimelineEvent(
                event_type="workflow.planned",
                message="Supervisor planned a workflow manifest from subagent proposals.",
                attributes={"proposal_count": len(proposals), "token_ref": request.token_ref},
            ),
            WorkflowTimelineEvent(
                event_type="workflow.awaiting_approval",
                message="Workflow manifest is awaiting human approval.",
                attributes={"required_scopes": authorization.scopes},
            ),
        ],
    )
    store[workflow_id] = record

    await _emit_sidecar_event(
        settings=settings,
        event_type="workflow.planned",
        user_id=request.user_id,
        session_id=request.session_id,
        tenant_id=request.tenant_id,
        workflow_id=workflow_id,
        plan_hash=hashed_plan,
        attributes={"proposal_count": len(proposals), "token_ref": request.token_ref},
    )
    await _emit_sidecar_event(
        settings=settings,
        event_type="workflow.awaiting_approval",
        user_id=request.user_id,
        session_id=request.session_id,
        tenant_id=request.tenant_id,
        workflow_id=workflow_id,
        plan_hash=hashed_plan,
        attributes={"required_scopes": authorization.scopes},
    )

    return record


@router.post("/workflows/{workflow_id}/approve", response_model=WorkflowRecord)
async def approve_workflow(
    workflow_id: str,
    request: WorkflowApprovalRequest,
    settings: Annotated[SupervisorSettings, Depends(get_settings)],
    store: Annotated[WorkflowStore, Depends(get_workflow_store)],
) -> WorkflowRecord:
    record = _require_workflow(store, workflow_id)
    if request.plan_hash != record.plan_hash:
        raise HTTPException(status_code=409, detail="plan_hash does not match workflow manifest")

    if not request.approved:
        updated = _append_event(
            record.model_copy(update={"status": WorkflowStatus(status="cancelled")}),
            event_type="workflow.cancelled",
            message="Workflow approval was declined.",
            attributes={"approved": False},
        )
        store[workflow_id] = updated
        return updated

    approval = ApprovedWorkflow(
        workflow_id=workflow_id,
        approval_id=f"approval:{workflow_id}",
        plan_hash=record.plan_hash,
        approved_by_user_id=request.approved_by_user_id,
        approved_scopes=record.authorization.scopes,
    )
    approved = _append_event(
        record.model_copy(
            update={
                "status": WorkflowStatus(status="approved"),
                "approved_workflow": approval,
            }
        ),
        event_type="workflow.approved",
        message="Human approval recorded for workflow manifest.",
        attributes={"approval_id": approval.approval_id, "token_ref": request.token_ref},
    )
    await _emit_sidecar_event(
        settings=settings,
        event_type="workflow.approved",
        user_id=approved.plan.user_id,
        session_id=approved.plan.session_id,
        tenant_id=approved.plan.tenant_id,
        workflow_id=workflow_id,
        plan_hash=record.plan_hash,
        approval_id=approval.approval_id,
        attributes={"token_ref": request.token_ref},
    )

    executed = await _execute_workflow(settings=settings, record=approved)
    store[workflow_id] = executed
    return executed


@router.get("/workflows/{workflow_id}", response_model=WorkflowRecord)
async def get_workflow(
    workflow_id: str,
    store: Annotated[WorkflowStore, Depends(get_workflow_store)],
) -> WorkflowRecord:
    return _require_workflow(store, workflow_id)


def _require_workflow(store: WorkflowStore, workflow_id: str) -> WorkflowRecord:
    record = store.get(workflow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return record


def _step_from_proposal(index: int, proposal: ToolProposal) -> WorkflowStep:
    required_scopes = _required_scopes(proposal)
    return WorkflowStep(
        step_id=f"step-{index:03d}",
        target_agent=proposal.agent_name,
        action=proposal.tool_name,
        input_model_type=f"{proposal.tool_name}.arguments",
        input_payload_json=json.dumps(
            proposal.arguments,
            sort_keys=True,
            separators=(",", ":"),
        ),
        required_scopes=required_scopes,
    )


def _required_scopes(proposal: ToolProposal) -> list[str]:
    requirements = _scope_requirements_for_tool(proposal.tool_name)
    try:
        return materialize_scopes_for_proposal(proposal, requirements)
    except ScopeMaterializationError:
        return []


def _scope_requirements_for_tool(tool_name: str) -> list[ScopeRequirement]:
    if tool_name == "get_identity_profile":
        return [
            ScopeRequirement(
                scope_template="DOE.Identity.{subject_user_id}",
                scope_args=["subject_user_id"],
                op="READ",
                hitl_description="Read identity profile for selected user ID",
            )
        ]
    if tool_name == "get_developer_app":
        return [
            ScopeRequirement(
                scope_template="DOE.Developer.{appid}",
                scope_args=["appid"],
                op="READ",
                hitl_description="Read developer app metadata for selected app ID",
            )
        ]
    if tool_name == "get_account_balance":
        return [
            ScopeRequirement(
                scope_template="DOE.Billing.{account_id}",
                scope_args=["account_id"],
                op="READ",
                hitl_description="Read billing balance for selected account ID",
            )
        ]
    if tool_name == "propose_workflow_plan":
        return [
            ScopeRequirement(
                scope_template="DOE.Workflow.plan",
                scope_args=[],
                op="READ",
                hitl_description="Review the user request and propose workflow steps",
            )
        ]
    return [
        ScopeRequirement(
            scope_template="DOE.Workflow.inspect",
            scope_args=[],
            op="READ",
            hitl_description="Inspect the user request for workflow planning",
        )
    ]


async def _execute_workflow(
    *,
    settings: SupervisorSettings,
    record: WorkflowRecord,
) -> WorkflowRecord:
    executing = record.model_copy(update={"status": WorkflowStatus(status="executing")})
    step_results = list(executing.step_results)
    events = list(executing.events)

    for step in executing.plan.steps:
        arguments = cast(dict[str, object], json.loads(step.input_payload_json))
        result = WorkflowStepExecutionResult(
            step_id=step.step_id,
            target_agent=step.target_agent,
            action=step.action,
            output={
                "target_agent": step.target_agent,
                "tool_name": step.action,
                "arguments": arguments,
                "deterministic": True,
            },
        )
        step_results.append(result)
        events.append(
            WorkflowTimelineEvent(
                event_type="workflow.step_executed",
                message=f"Executed {step.action} on {step.target_agent}.",
                step_id=step.step_id,
                attributes={"target_agent": step.target_agent, "action": step.action},
            )
        )
        await _emit_sidecar_event(
            settings=settings,
            event_type="workflow.step_executed",
            user_id=executing.plan.user_id,
            session_id=executing.plan.session_id,
            tenant_id=executing.plan.tenant_id,
            workflow_id=executing.workflow_id,
            step_id=step.step_id,
            plan_hash=executing.plan_hash,
            approval_id=(
                executing.approved_workflow.approval_id
                if executing.approved_workflow is not None
                else None
            ),
            attributes={"target_agent": step.target_agent, "action": step.action},
        )

    events.append(
        WorkflowTimelineEvent(
            event_type="workflow.completed",
            message="Workflow completed deterministically in manifest order.",
            attributes={"step_count": len(executing.plan.steps)},
        )
    )
    completed = executing.model_copy(
        update={
            "status": WorkflowStatus(status="completed"),
            "events": events,
            "step_results": step_results,
            "updated_at": datetime.now(UTC),
        }
    )
    await _emit_sidecar_event(
        settings=settings,
        event_type="workflow.completed",
        user_id=completed.plan.user_id,
        session_id=completed.plan.session_id,
        tenant_id=completed.plan.tenant_id,
        workflow_id=completed.workflow_id,
        plan_hash=completed.plan_hash,
        approval_id=(
            completed.approved_workflow.approval_id
            if completed.approved_workflow is not None
            else None
        ),
        attributes={"step_count": len(completed.plan.steps)},
    )
    return completed


def _append_event(
    record: WorkflowRecord,
    *,
    event_type: str,
    message: str,
    attributes: dict[str, object],
) -> WorkflowRecord:
    events = list(record.events)
    events.append(
        WorkflowTimelineEvent(
            event_type=event_type,
            message=message,
            attributes=attributes,
        )
    )
    return record.model_copy(update={"events": events, "updated_at": datetime.now(UTC)})


async def _emit_sidecar_event(
    *,
    settings: SupervisorSettings,
    event_type: str,
    user_id: str,
    session_id: str,
    tenant_id: str | None = None,
    workflow_id: str | None = None,
    step_id: str | None = None,
    plan_hash: str | None = None,
    approval_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> None:
    if not settings.observability_sidecar_url:
        return

    event = WorkflowEvent(
        event_id=f"evt-{uuid4().hex}",
        event_type=event_type,
        user_id=user_id,
        session_id=session_id,
        tenant_id=tenant_id,
        workflow_id=workflow_id,
        step_id=step_id,
        agent_name="supervisor",
        agentic_span_id=f"{event_type}:{workflow_id or session_id}",
        plan_hash=plan_hash,
        approval_id=approval_id,
        attributes=attributes or {},
    )
    try:
        async with ObservabilitySidecarClient(
            base_url=settings.observability_sidecar_url
        ) as sidecar:
            await sidecar.emit_trace(source_component="supervisor", event=event)
            await sidecar.emit_log(
                source_component="supervisor",
                level="info",
                message=event_type,
                attributes=attributes or {},
                trace_id=event.trace_id,
                agentic_span_id=event.agentic_span_id,
            )
    except httpx.HTTPError:
        return

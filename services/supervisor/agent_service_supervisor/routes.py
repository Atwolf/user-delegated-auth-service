from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any, cast
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from observability.models import WorkflowEvent
from observability.sidecar_client import ObservabilitySidecarClient
from workflow_core import (
    ApprovedWorkflow,
    AuthorizationBundle,
    ScopeMaterializationError,
    ToolProposal,
    WorkflowPlan,
    WorkflowStatus,
    WorkflowStep,
    materialize_scopes_for_proposal,
    plan_hash,
    scope_requirements_for_auth0_token,
    scope_requirements_for_tool,
)

from agent_service_supervisor.config import SupervisorSettings
from agent_service_supervisor.discovery_sqlite import (
    SubagentDiscoveryService,
    SubagentRecord,
)
from agent_service_supervisor.workflow_api_models import (
    Auth0UserSessionMetadataRequest,
    Auth0UserSessionMetadataResult,
    UserPersona,
    WorkflowApprovalRequest,
    WorkflowPlanRequest,
    WorkflowRecord,
    WorkflowTimelineEvent,
)
from agent_service_supervisor.workflow_orchestrator import WorkflowOrchestrator

router = APIRouter()
ORCHESTRATION_TOOL_NAMES = frozenset({"inspect_request", "propose_workflow_plan"})
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
    "/identity/auth0/session",
    response_model=Auth0UserSessionMetadataResult,
)
async def load_auth0_user_session_metadata(
    request: Auth0UserSessionMetadataRequest,
    settings: Annotated[SupervisorSettings, Depends(get_settings)],
) -> Auth0UserSessionMetadataResult:
    await _emit_sidecar_event(
        settings=settings,
        event_type="frontend.auth0_user_login_succeeded",
        user_id=request.user_id,
        session_id=request.session_id,
        attributes={
            "scope_count": len(request.token_scopes),
            "audience": request.audience,
        },
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        metadata = await _load_auth0_user_metadata(
            client=client,
            settings=settings,
            user_id=request.user_id,
        )

    metadata_scopes = _metadata_string_list(metadata, "allowed_scopes")
    metadata_tools = _metadata_string_list(metadata, "allowed_mcp_tools")
    issued_scopes = metadata_scopes or request.token_scopes
    persona = _build_user_persona(
        claims={"name": request.user_name} if request.user_name else {},
        id_claims={"email": request.user_email} if request.user_email else {},
        metadata=metadata,
        user_id=request.user_id,
        email=request.user_email,
        scopes=issued_scopes,
        allowed_tools=metadata_tools,
    )

    await _emit_sidecar_event(
        settings=settings,
        event_type="identity.auth0_user_session_materialized",
        user_id=request.user_id,
        session_id=request.session_id,
        attributes={
            "scopes": issued_scopes,
            "audience": request.audience,
            "token_ref": request.token_ref,
            "allowed_tools": metadata_tools,
        },
    )
    await _emit_sidecar_event(
        settings=settings,
        event_type="on_login",
        user_id=request.user_id,
        session_id=request.session_id,
        attributes={
            "display_name": persona.display_name,
            "headline": persona.headline,
            "traits": persona.traits,
            "allowed_tools": metadata_tools,
            "scope_count": len(issued_scopes),
        },
    )

    return Auth0UserSessionMetadataResult(
        scope=" ".join(issued_scopes),
        audience=request.audience,
        token_ref=request.token_ref,
        user_id=request.user_id,
        user_email=request.user_email,
        allowed_tools=metadata_tools,
        persona=persona,
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
    discovered_proposals = [
        ToolProposal.model_validate(proposal)
        for proposal in await orchestrator.request_tool_proposals(
            user_query=request.question,
            user_id=request.user_id,
            session_id=request.session_id,
            subagents=subagents,
        )
    ]
    proposals = _filter_proposals_by_allowed_tools(
        discovered_proposals,
        request.allowed_tools,
    )
    steps = [
        _step_from_proposal(index, proposal, request.token_scopes)
        for index, proposal in enumerate(proposals, 1)
    ]
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
                attributes={
                    "proposal_count": len(proposals),
                    "filtered_proposal_count": len(discovered_proposals) - len(proposals),
                    "token_ref": request.token_ref,
                    "issued_scope_count": len(request.token_scopes),
                },
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
        attributes={
            "proposal_count": len(proposals),
            "filtered_proposal_count": len(discovered_proposals) - len(proposals),
            "token_ref": request.token_ref,
            "issued_scope_count": len(request.token_scopes),
        },
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

    delegated = _append_event(
        approved,
        event_type="workflow.execution_delegated",
        message=(
            "Workflow approval was recorded; execution is delegated to the target "
            "agent service and egress gateway runtime."
        ),
        attributes={"approval_id": approval.approval_id},
    )
    store[workflow_id] = delegated
    return delegated


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


def _step_from_proposal(
    index: int,
    proposal: ToolProposal,
    token_scopes: list[str],
) -> WorkflowStep:
    required_scopes = _required_scopes(proposal, token_scopes)
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


def _filter_proposals_by_allowed_tools(
    proposals: list[ToolProposal],
    allowed_tools: list[str] | None,
) -> list[ToolProposal]:
    if allowed_tools is None:
        return proposals
    allowed_tool_names = set(allowed_tools).union(ORCHESTRATION_TOOL_NAMES)
    return [proposal for proposal in proposals if proposal.tool_name in allowed_tool_names]


def _required_scopes(proposal: ToolProposal, token_scopes: list[str]) -> list[str]:
    requirements = (
        scope_requirements_for_auth0_token(proposal.tool_name, token_scopes)
        if token_scopes
        else scope_requirements_for_tool(proposal.tool_name)
    )
    try:
        return materialize_scopes_for_proposal(proposal, requirements)
    except ScopeMaterializationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"could not materialize workflow scopes for {proposal.tool_name}: {exc}",
        ) from exc


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


def _required_auth0_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise HTTPException(status_code=502, detail="Auth0 token response missing required field")
    return value


async def _load_auth0_user_metadata(
    *,
    client: httpx.AsyncClient,
    settings: SupervisorSettings,
    user_id: str,
) -> dict[str, object]:
    domain = _auth0_domain(settings.auth0_domain)
    client_id = _required_auth0_management_setting(
        settings.auth0_management_client_id,
        "AUTH0_MANAGEMENT_CLIENT_ID",
    )
    client_secret = _required_auth0_management_setting(
        settings.auth0_management_client_secret,
        "AUTH0_MANAGEMENT_CLIENT_SECRET",
    )
    audience = settings.auth0_management_audience or f"https://{domain}/api/v2/"

    management_token_response = await client.post(
        f"https://{domain}/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "audience": audience,
            "scope": "read:users read:users_app_metadata",
        },
    )
    try:
        management_token_response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=_auth0_error_detail(exc.response),
        ) from exc

    management_payload = cast(dict[str, Any], management_token_response.json())
    management_token = _required_auth0_string(management_payload, "access_token")
    user_response = await client.get(
        f"https://{domain}/api/v2/users/{quote(user_id, safe='')}",
        headers={"authorization": f"Bearer {management_token}"},
    )
    try:
        user_response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=_auth0_error_detail(exc.response),
        ) from exc

    user_payload = cast(dict[str, Any], user_response.json())
    app_metadata = user_payload.get("app_metadata")
    if not isinstance(app_metadata, dict):
        return {}
    magnum_opus = cast(dict[str, object], app_metadata).get("magnum_opus")
    if not isinstance(magnum_opus, dict):
        return {}
    return cast(dict[str, object], magnum_opus)


def _required_auth0_management_setting(value: str | None, name: str) -> str:
    if value and value.strip():
        return value.strip()
    raise HTTPException(
        status_code=500,
        detail=f"{name} is required for Auth0 metadata loading",
    )


def _auth0_domain(value: str | None) -> str:
    domain = _required_auth0_management_setting(value, "AUTH0_DOMAIN")
    return domain.removeprefix("https://").removeprefix("http://").rstrip("/")


def _build_user_persona(
    *,
    claims: dict[str, object],
    id_claims: dict[str, object],
    metadata: dict[str, object],
    user_id: str,
    email: str | None,
    scopes: list[str],
    allowed_tools: list[str],
) -> UserPersona:
    display_name = (
        _metadata_string(metadata, "display_name")
        or _claim_string("name", claims, id_claims)
        or _claim_string("nickname", claims, id_claims)
        or (email.split("@", 1)[0] if email else None)
        or user_id
    )
    metadata_traits = _metadata_string_list(metadata, "persona_traits")
    traits = metadata_traits or _persona_traits_from_session(scopes, allowed_tools, email)
    headline = _metadata_string(metadata, "persona_headline") or _persona_headline(
        display_name=display_name,
        traits=traits,
        allowed_tools=allowed_tools,
    )
    greeting = _metadata_string(metadata, "persona_greeting") or _persona_greeting(
        display_name=display_name,
        traits=traits,
    )

    return UserPersona(
        display_name=display_name,
        headline=headline,
        greeting=greeting,
        traits=traits,
    )


def _claim_string(key: str, *claims_values: dict[str, object]) -> str | None:
    for claims in claims_values:
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _metadata_string(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _metadata_string_list(metadata: dict[str, object], key: str) -> list[str]:
    value = metadata.get(key)
    if not isinstance(value, list):
        return []
    values = cast(list[object], value)
    return sorted({item.strip() for item in values if isinstance(item, str) and item.strip()})


def _persona_traits_from_session(
    scopes: list[str],
    allowed_tools: list[str],
    email: str | None,
) -> list[str]:
    traits: list[str] = []
    if email:
        traits.append(f"email: {email}")
    if scopes:
        traits.append(f"{len(scopes)} approved scope{'s' if len(scopes) != 1 else ''}")
    if allowed_tools:
        tool_count = len(allowed_tools)
        suffix = "s" if tool_count != 1 else ""
        traits.append(f"{tool_count} MCP tool{suffix} available")
    return traits[:4]


def _persona_headline(
    *,
    display_name: str,
    traits: list[str],
    allowed_tools: list[str],
) -> str:
    if allowed_tools:
        return (
            f"{display_name} is cleared for {len(allowed_tools)} workflow tool"
            f"{'s' if len(allowed_tools) != 1 else ''}: {', '.join(allowed_tools[:3])}."
        )
    if traits:
        return f"{display_name} signed in with {', '.join(traits[:2])}."
    return f"{display_name} signed in with an Auth0-backed identity."


def _persona_greeting(*, display_name: str, traits: list[str]) -> str:
    if traits:
        return f"Welcome back, {display_name}. I tuned this workspace around {traits[0]}."
    return f"Welcome back, {display_name}. I am ready to plan workflows for this session."


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


def _auth0_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "Auth0 token exchange failed"

    if not isinstance(payload, dict):
        return "Auth0 token exchange failed"

    error_payload = cast(dict[str, object], payload)
    error = error_payload.get("error")
    description = error_payload.get("error_description")
    details = [
        item
        for item in (error, description)
        if isinstance(item, str) and item.strip()
    ]
    if not details:
        return "Auth0 token exchange failed"

    return "Auth0 token exchange failed: " + " - ".join(details)

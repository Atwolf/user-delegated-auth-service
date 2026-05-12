from __future__ import annotations

from typing import Annotated, Any, cast
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from observability.models import WorkflowEvent
from observability.sidecar_client import ObservabilitySidecarClient
from session_state import (
    SESSION_CONTEXT_HEADER,
    SESSION_CONTEXT_SIGNATURE_HEADER,
    InternalAuthError,
    TrustedSessionContext,
    verify_session_context,
)

from agent_service_supervisor.config import SupervisorSettings
from agent_service_supervisor.workflow_api_models import (
    Auth0UserSessionMetadataRequest,
    Auth0UserSessionMetadataResult,
    UserPersona,
)

router = APIRouter()


def get_settings(request: Request) -> SupervisorSettings:
    return cast(SupervisorSettings, request.app.state.settings)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/identity/auth0/session",
    response_model=Auth0UserSessionMetadataResult,
)
async def load_auth0_user_session_metadata(
    request: Auth0UserSessionMetadataRequest,
    http_request: Request,
    settings: Annotated[SupervisorSettings, Depends(get_settings)],
) -> Auth0UserSessionMetadataResult:
    trusted_context = _trusted_context_from_request(http_request, settings)
    _assert_metadata_request_matches_trusted_context(request, trusted_context)

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

    issued_scopes = _required_metadata_string_list(metadata, "allowed_scopes")
    metadata_tools = _required_metadata_string_list(metadata, "allowed_mcp_tools")
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


def _trusted_context_from_request(
    request: Request,
    settings: SupervisorSettings,
) -> TrustedSessionContext:
    try:
        return verify_session_context(
            encoded_context=request.headers.get(SESSION_CONTEXT_HEADER),
            signature=request.headers.get(SESSION_CONTEXT_SIGNATURE_HEADER),
            secret=settings.internal_service_auth_secret or "",
        )
    except InternalAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _assert_metadata_request_matches_trusted_context(
    request: Auth0UserSessionMetadataRequest,
    context: TrustedSessionContext,
) -> None:
    mismatches = [
        key
        for key, body_value, context_value in (
            ("session_id", request.session_id, context.session_id),
            ("tenant_id", request.tenant_id, context.tenant_id),
            ("token_ref", request.token_ref, context.token_ref),
            ("token_scopes", request.token_scopes, context.token_scopes),
            ("user_id", request.user_id, context.user_id),
        )
        if body_value != context_value
    ]
    if mismatches:
        raise HTTPException(
            status_code=403,
            detail="Auth0 metadata request does not match trusted session context: "
            + ", ".join(mismatches),
        )


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
        raise HTTPException(
            status_code=403,
            detail="Auth0 user metadata is missing app_metadata.magnum_opus",
        )
    magnum_opus = cast(dict[str, object], app_metadata).get("magnum_opus")
    if not isinstance(magnum_opus, dict):
        raise HTTPException(
            status_code=403,
            detail="Auth0 user metadata is missing app_metadata.magnum_opus",
        )
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


def _required_metadata_string_list(metadata: dict[str, object], key: str) -> list[str]:
    values = _metadata_string_list(metadata, key)
    if not values:
        raise HTTPException(
            status_code=403,
            detail=f"Auth0 user metadata field app_metadata.magnum_opus.{key} is required",
        )
    return values


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
                attributes=event.attributes,
                agentic_span_id=event.agentic_span_id,
            )
    except (httpx.HTTPError, RuntimeError):
        return


def _auth0_error_detail(response: httpx.Response) -> str:
    try:
        payload = cast(object, response.json())
    except ValueError:
        return response.text
    if isinstance(payload, dict):
        typed_payload = cast(dict[str, object], payload)
        for key in ("error_description", "message", "error"):
            value = typed_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return response.text

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastmcp import Client
from session_state import (
    SESSION_CONTEXT_HEADER,
    SESSION_CONTEXT_SIGNATURE_HEADER,
    InternalAuthError,
    TrustedSessionContext,
    verify_session_context,
)
from workflow_core import (
    ExecutionGrant,
    ExecutionGrantError,
    ToolAuthorizationSpec,
    get_tool_authorization,
    verify_execution_grant,
)

from egress_gateway.models import EgressRequest, EgressResponse

READ_LIKE_PRIMITIVES = frozenset(
    {
        "discover",
        "discovery",
        "get",
        "list",
        "read",
        "retrieve",
        "search",
    }
)
MUTATION_PRIMITIVES = frozenset(
    {
        "create",
        "delete",
        "execute",
        "invoke",
        "mutate",
        "mutation",
        "patch",
        "post",
        "put",
        "run",
        "update",
        "write",
    }
)
MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
REDACTED_HEADER_VALUE = "[REDACTED]"


def create_app() -> FastAPI:
    app = FastAPI(title="Egress Gateway")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/egress/mcp", response_model=EgressResponse)
    async def egress_mcp(payload: EgressRequest, request: Request) -> EgressResponse:
        trusted_context = _trusted_context_from_request(request)
        response = derive_outbound_request(payload, trusted_context)
        response.outbound["mcp_result"] = await _call_mcp_tool(payload)
        return response

    return app


def derive_outbound_request(
    payload: EgressRequest,
    trusted_context: TrustedSessionContext,
) -> EgressResponse:
    method = payload.method.upper()
    primitive = payload.primitive.lower()
    headers: dict[str, str] = {}
    tool_authorization = _required_tool_authorization(payload.tool_name)

    if _is_mcp_call_boundary(primitive, method, tool_authorization):
        if (
            tool_authorization.downstream_audience
            and payload.target_mcp != tool_authorization.downstream_audience
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="target_mcp does not match tool authorization catalog",
            )
        _authorize_execution(payload, trusted_context)

    if _is_read_boundary(primitive, method) and payload.obo_token_ref:
        headers["X-AuthN-Context"] = REDACTED_HEADER_VALUE

    headers["Authorization"] = REDACTED_HEADER_VALUE

    return EgressResponse(
        primitive=payload.primitive,
        method=method,
        target_mcp=payload.target_mcp,
        tool_name=payload.tool_name,
        arguments=payload.arguments,
        workflow_id=payload.workflow_id,
        approval_id=payload.approval_id,
        obo_token_ref=payload.obo_token_ref,
        outbound={
            "method": method,
            "target_mcp": payload.target_mcp,
            "tool_name": payload.tool_name,
            "headers": headers,
            "arguments": payload.arguments,
        },
    )


def _authorize_execution(
    payload: EgressRequest,
    trusted_context: TrustedSessionContext,
) -> None:
    if not payload.access_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access_token is required for outbound MCP execution",
        )
    grant = payload.execution_grant
    if grant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="execution_grant is required for outbound MCP execution",
        )
    try:
        verify_execution_grant(
            grant,
            signature=payload.execution_grant_signature,
            secret=_internal_auth_secret(),
        )
    except ExecutionGrantError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    _assert_grant_matches_request(payload, grant, trusted_context)


def _assert_grant_matches_request(
    payload: EgressRequest,
    grant: ExecutionGrant,
    trusted_context: TrustedSessionContext,
) -> None:
    if grant.expires_at is not None and grant.expires_at <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="execution grant has expired",
        )

    expected = {
        "approval_id": payload.approval_id,
        "arguments": payload.arguments,
        "method": payload.method.upper(),
        "primitive": payload.primitive.upper(),
        "target_mcp": payload.target_mcp,
        "tool_name": payload.tool_name,
        "workflow_id": payload.workflow_id,
    }
    actual = {
        "approval_id": grant.approval_id,
        "arguments": grant.arguments,
        "method": grant.method,
        "primitive": grant.primitive,
        "target_mcp": grant.target_mcp,
        "tool_name": grant.tool_name,
        "workflow_id": grant.workflow_id,
    }
    mismatches = sorted(
        key for key, expected_value in expected.items() if actual[key] != expected_value
    )
    if mismatches:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"execution grant does not match request: {', '.join(mismatches)}",
        )

    context_mismatches = [
        key
        for key, grant_value, context_value in (
            ("session_id", grant.session_id, trusted_context.session_id),
            ("tenant_id", grant.tenant_id, trusted_context.tenant_id),
            ("user_id", grant.user_id, trusted_context.user_id),
        )
        if grant_value != context_value
    ]
    if context_mismatches:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "execution grant does not match trusted session context: "
                + ", ".join(context_mismatches)
            ),
        )

    missing_scopes = sorted(set(grant.required_scopes).difference(payload.token_scopes))
    if missing_scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access token is missing grant-required scopes",
        )

    if not grant.audience:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="execution grant audience is required",
        )
    if payload.token_audience != grant.audience:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access token audience does not match execution grant",
        )


def _is_read_boundary(primitive: str, method: str) -> bool:
    return primitive in READ_LIKE_PRIMITIVES or method == "GET"


def _is_mcp_call_boundary(
    primitive: str,
    method: str,
    tool_authorization: ToolAuthorizationSpec | None,
) -> bool:
    if tool_authorization is not None:
        return True
    if primitive in MUTATION_PRIMITIVES or method in MUTATION_METHODS:
        return True
    return False


def _required_tool_authorization(tool_name: str) -> ToolAuthorizationSpec:
    try:
        return get_tool_authorization(tool_name)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="known tool authorization is required for outbound MCP execution",
        ) from None


def _internal_auth_secret() -> str:
    return os.getenv("INTERNAL_SERVICE_AUTH_SECRET") or ""


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


async def _call_mcp_tool(payload: EgressRequest) -> dict[str, Any]:
    url = _mcp_url(payload.target_mcp)
    try:
        mcp_endpoint = f"{url.rstrip('/')}/mcp"
        async with Client(mcp_endpoint, auth=f"Bearer {payload.access_token}") as client:
            result = await client.call_tool(
                payload.tool_name,
                payload.arguments,
                raise_on_error=False,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MCP transport call failed: {type(exc).__name__}",
        ) from exc

    return {
        "status": "failed" if result.is_error else "completed",
        "is_error": result.is_error,
        "data": result.data,
        "structured_content": result.structured_content,
        "content": [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else str(item)
            for item in result.content
        ],
    }


def _mcp_url(target_mcp: str) -> str:
    if target_mcp == "network-mcp":
        return os.getenv("NETWORK_MCP_URL", "http://network-mcp:8011")
    if target_mcp == "cloud-mcp":
        return os.getenv("CLOUD_MCP_URL", "http://cloud-mcp:8012")
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"unsupported target_mcp: {target_mcp}",
    )


app = create_app()

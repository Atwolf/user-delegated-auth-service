from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastmcp import Client
from workflow_core import get_tool_authorization

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
    async def egress_mcp(payload: EgressRequest) -> EgressResponse:
        response = derive_outbound_request(payload)
        if _mcp_calls_enabled() and payload.access_token:
            response.outbound["mcp_result"] = await _call_mcp_tool(payload)
        return response

    return app


def derive_outbound_request(payload: EgressRequest) -> EgressResponse:
    method = payload.method.upper()
    primitive = payload.primitive.lower()
    headers: dict[str, str] = {}

    if _is_execution_boundary(primitive, method, payload.tool_name) and not payload.access_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access_token is required for outbound MCP execution",
        )

    if _is_read_boundary(primitive, method) and payload.obo_token_ref:
        headers["X-AuthN-Context"] = REDACTED_HEADER_VALUE

    if _is_execution_boundary(primitive, method, payload.tool_name):
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


def _is_read_boundary(primitive: str, method: str) -> bool:
    return primitive in READ_LIKE_PRIMITIVES or method == "GET"


def _is_execution_boundary(primitive: str, method: str, tool_name: str) -> bool:
    if get_tool_authorization(tool_name).op in {"WRITE", "ADMIN"}:
        return True
    return primitive in MUTATION_PRIMITIVES or method in MUTATION_METHODS


def _mcp_calls_enabled() -> bool:
    return os.getenv("EGRESS_CALL_MCP_TOOLS", "").casefold() in {"1", "true", "yes"}


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
        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }

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

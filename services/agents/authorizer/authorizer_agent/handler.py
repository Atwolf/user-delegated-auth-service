from __future__ import annotations

from authorizer_agent.app import AuthorizationGateRequest, AuthorizationGateResponse


class AuthorizerHandler:
    async def authorize(self, request: AuthorizationGateRequest) -> AuthorizationGateResponse:
        return AuthorizationGateResponse(
            approval_id=f"approval:{request.workflow_id}",
            approved_scopes=sorted(set(request.scopes)),
        )

from __future__ import annotations

from fastapi import HTTPException, Request, status

from gateway_app.schemas import UserContext


def user_context_from_request(request: Request) -> UserContext:
    token = bearer_token(request.headers.get("authorization"))
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is required for the AG-UI gateway",
        )

    user_id = request.headers.get("x-user-id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id is required for the AG-UI gateway",
        )
    return UserContext(user_id=user_id)


def bearer_token(value: str | None) -> str | None:
    if value is None:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.casefold() != "bearer" or not token.strip():
        return None
    return token.strip()

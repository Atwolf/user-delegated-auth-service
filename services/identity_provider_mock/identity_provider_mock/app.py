from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title="Auth0 Mock Identity Provider")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/.well-known/openid-configuration")
async def discovery() -> dict[str, str]:
    return {
        "issuer": "http://auth0-mock:8099/",
        "authorization_endpoint": "http://auth0-mock:8099/authorize",
        "token_endpoint": "http://auth0-mock:8099/oauth/token",
        "jwks_uri": "http://auth0-mock:8099/.well-known/jwks.json",
    }


@app.get("/.well-known/jwks.json")
async def jwks() -> dict[str, list[dict[str, object]]]:
    return {"keys": []}


@app.post("/oauth/token")
async def token(request: Request) -> dict[str, str | int]:
    form = parse_qs((await request.body()).decode("utf-8"))
    grant_type = _form_value(form, "grant_type")
    client_id = _form_value(form, "client_id")
    client_secret = _form_value(form, "client_secret")
    scope = _form_value(form, "scope") or "openid profile email"

    if grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="unsupported grant_type")
    if not client_id or not client_secret:
        raise HTTPException(status_code=401, detail="invalid client credentials")

    return {
        "access_token": f"mock-access-token-for-{client_id}",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": scope,
    }


def _form_value(form: dict[str, list[str]], key: str) -> str:
    values = form.get(key, [])
    return values[0] if values else ""

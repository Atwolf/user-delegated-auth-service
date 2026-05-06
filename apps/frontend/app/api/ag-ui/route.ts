import { NextResponse } from "next/server";
import { parseScopeString } from "@/lib/auth0-config";
import { readAuth0SessionCookie } from "@/lib/server/auth0-session";

export const maxDuration = 30;

const agUiGatewayUrl = () =>
  (process.env.AG_UI_GATEWAY_URL ??
    process.env.NEXT_PUBLIC_AG_UI_GATEWAY_URL ??
    "http://127.0.0.1:8088/agent").replace(/\/+$/, "");

export async function POST(req: Request) {
  const session = readAuth0SessionCookie(req.headers.get("cookie"));
  if (!session) {
    return NextResponse.json({ error: "Auth0 user login is required" }, { status: 401 });
  }

  const payload = (await req.json()) as Record<string, unknown>;
  const state =
    payload.state && typeof payload.state === "object"
      ? (payload.state as Record<string, unknown>)
      : {};

  const response = await fetch(agUiGatewayUrl(), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      ...payload,
      state: {
        ...state,
        allowed_tools: [...new Set(session.allowedTools)].sort(),
        auth_context_ref: session.authContextRef,
        session_id: session.sessionId,
        token_ref: session.tokenRef,
        token_scopes: parseScopeString(session.scope),
        user_id: session.userId
      }
    }),
    cache: "no-store"
  });

  return new Response(response.body, {
    status: response.status,
    headers: {
      "cache-control": "no-cache",
      "content-type": response.headers.get("content-type") ?? "text/event-stream"
    }
  });
}

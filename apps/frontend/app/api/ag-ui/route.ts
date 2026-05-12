import { NextResponse } from "next/server";
import { readAuth0SessionCookie } from "@/lib/server/auth0-session";
import { signedSessionContextHeaders } from "@/lib/server/internal-auth";
import { sanitizeBrowserRecord } from "@/lib/server/redaction";
import { sanitizedSessionContext } from "@/lib/server/supervisor";

export const maxDuration = 30;

const agUiGatewayUrl = () =>
  (process.env.AG_UI_GATEWAY_URL ?? "http://127.0.0.1:8088/agent").replace(/\/+$/, "");

export async function POST(req: Request) {
  const session = readAuth0SessionCookie(req.headers.get("cookie"));
  if (!session) {
    return NextResponse.json({ error: "Auth0 user login is required" }, { status: 401 });
  }

  const payload = sanitizeRecord(await req.json().catch(() => ({})));
  const state = publicAgUiState(isRecord(payload.state) ? payload.state : {});
  const context = sanitizedSessionContext(session);
  const correlationId =
    typeof payload.runId === "string"
      ? payload.runId
      : typeof payload.run_id === "string"
        ? payload.run_id
        : crypto.randomUUID();

  const response = await fetch(agUiGatewayUrl(), {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...signedSessionContextHeaders(context, correlationId)
    },
    body: JSON.stringify(agUiGatewayPayload(payload, state)),
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

function sanitizeRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? sanitizeBrowserRecord(value) : {};
}

function publicAgUiState(state: Record<string, unknown>): Record<string, unknown> {
  const blocked = new Set([
    "allowed_tools",
    "allowedTools",
    "session_id",
    "sessionId",
    "tenant_id",
    "tenantId",
    "token_ref",
    "tokenRef",
    "token_scopes",
    "tokenScopes",
    "user_id",
    "userId"
  ]);
  return Object.fromEntries(Object.entries(state).filter(([key]) => !blocked.has(key)));
}

function agUiGatewayPayload(
  payload: Record<string, unknown>,
  state: Record<string, unknown>
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    messages: Array.isArray(payload.messages) ? payload.messages : [],
    state
  };

  if (typeof payload.threadId === "string") {
    body.threadId = payload.threadId;
  } else if (typeof payload.thread_id === "string") {
    body.thread_id = payload.thread_id;
  }

  if (typeof payload.runId === "string") {
    body.runId = payload.runId;
  } else if (typeof payload.run_id === "string") {
    body.run_id = payload.run_id;
  }

  return body;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

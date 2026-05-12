import { NextResponse } from "next/server";
import type { Auth0BrowserSession, Auth0UserSession } from "@/lib/auth0-config";
import { readAuth0SessionCookie } from "@/lib/server/auth0-session";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const session = readAuth0SessionCookie(req.headers.get("cookie"));
  if (!session) return NextResponse.json({ session: null });
  return NextResponse.json({ session: browserSession(session) });
}

function browserSession(session: Auth0UserSession): Auth0BrowserSession {
  return {
    allowedTools: session.allowedTools,
    audience: session.audience,
    expiresAt: session.expiresAt,
    persona: session.persona,
    scope: session.scope,
    sessionId: session.sessionId,
    tenantId: session.tenantId ?? null,
    userEmail: session.userEmail,
    userId: session.userId
  };
}

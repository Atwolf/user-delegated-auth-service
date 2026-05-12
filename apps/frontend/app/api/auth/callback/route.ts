import { NextResponse } from "next/server";
import {
  auth0ErrorRedirect,
  exchangeCodeForSession,
  getAuth0UserAuthConfig,
  sessionMaxAgeSeconds,
  type Auth0Transaction
} from "@/lib/server/auth0-oidc";
import type { Auth0ServerSession, Auth0UserSession } from "@/lib/auth0-config";
import {
  AUTH0_SESSION_COOKIE,
  AUTH0_TRANSACTION_COOKIE,
  cookieOptions,
  createAuth0SessionCookieValue,
  createSessionId,
  expiredCookieOptions,
  getCookieValue,
  readSignedCookieValue
} from "@/lib/server/auth0-session";
import { registerAgentAuthContext } from "@/lib/server/supervisor";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const requestUrl = new URL(req.url);
  let config;
  try {
    config = getAuth0UserAuthConfig(requestUrl);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Auth0 callback is not configured";
    return NextResponse.json({ error: message }, { status: 500 });
  }

  const transaction = readSignedCookieValue<Auth0Transaction>(
    getCookieValue(req.headers.get("cookie"), AUTH0_TRANSACTION_COOKIE)
  );
  if (!transaction) {
    return redirectWithError(config, "Auth0 login state is missing or expired");
  }

  const state = requestUrl.searchParams.get("state");
  if (state !== transaction.state) {
    return redirectWithError(config, "Auth0 login state validation failed");
  }

  const auth0Error = requestUrl.searchParams.get("error");
  if (auth0Error) {
    const description = requestUrl.searchParams.get("error_description");
    return redirectWithError(
      config,
      ["Auth0 user login failed", auth0Error, description].filter(Boolean).join(": ")
    );
  }

  const code = requestUrl.searchParams.get("code");
  if (!code) {
    return redirectWithError(config, "Auth0 callback did not include an authorization code");
  }

  try {
    const session = await exchangeCodeForSession(config, transaction, code, createSessionId());
    await registerAgentAuthContext(session);
    const maxAge = sessionMaxAgeSeconds(session);
    const response = NextResponse.redirect(new URL(transaction.returnTo, config.appBaseUrl));
    response.cookies.set(
      AUTH0_SESSION_COOKIE,
      createAuth0SessionCookieValue(browserSession(session), maxAge),
      cookieOptions(maxAge)
    );
    response.cookies.set(AUTH0_TRANSACTION_COOKIE, "", expiredCookieOptions());
    return response;
  } catch (error) {
    const message = error instanceof Error ? error.message : "Auth0 user login failed";
    return redirectWithError(config, message);
  }
}

function browserSession(session: Auth0ServerSession): Auth0UserSession {
  return {
    allowedTools: session.allowedTools,
    audience: session.audience,
    expiresAt: session.expiresAt,
    persona: session.persona,
    scope: session.scope,
    sessionId: session.sessionId,
    tenantId: session.tenantId ?? null,
    tokenRef: session.tokenRef,
    userEmail: session.userEmail,
    userId: session.userId
  };
}

function redirectWithError(
  config: ReturnType<typeof getAuth0UserAuthConfig>,
  detail: string
): NextResponse {
  const response = NextResponse.redirect(auth0ErrorRedirect(config, detail));
  response.cookies.set(AUTH0_TRANSACTION_COOKIE, "", expiredCookieOptions());
  return response;
}

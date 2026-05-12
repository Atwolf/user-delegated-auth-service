import { NextResponse } from "next/server";
import { getAuth0UserAuthConfig } from "@/lib/server/auth0-oidc";
import {
  AUTH0_SESSION_COOKIE,
  AUTH0_TRANSACTION_COOKIE,
  expiredCookieOptions,
  readAuth0SessionCookie
} from "@/lib/server/auth0-session";
import { deleteAuth0Session } from "@/lib/server/auth0-session-store";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const requestUrl = new URL(req.url);
  const session = readAuth0SessionCookie(req.headers.get("cookie"));
  if (session) deleteAuth0Session(session.sessionId);
  const response = NextResponse.redirect(logoutUrl(requestUrl));
  response.cookies.set(AUTH0_SESSION_COOKIE, "", expiredCookieOptions());
  response.cookies.set(AUTH0_TRANSACTION_COOKIE, "", expiredCookieOptions());
  return response;
}

export async function POST(req: Request) {
  return GET(req);
}

function logoutUrl(requestUrl: URL): URL {
  try {
    const config = getAuth0UserAuthConfig(requestUrl);
    const url = new URL(`https://${config.domain}/v2/logout`);
    url.searchParams.set("client_id", config.clientId);
    url.searchParams.set("returnTo", config.appBaseUrl);
    return url;
  } catch {
    return new URL("/", requestUrl);
  }
}

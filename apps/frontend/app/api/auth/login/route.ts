import { NextResponse } from "next/server";
import {
  buildAuthorizationUrl,
  createAuth0Transaction,
  getAuth0UserAuthConfig
} from "@/lib/server/auth0-oidc";
import {
  AUTH0_TRANSACTION_COOKIE,
  cookieOptions,
  createSignedCookieValue
} from "@/lib/server/auth0-session";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  try {
    const requestUrl = new URL(req.url);
    const config = getAuth0UserAuthConfig(requestUrl);
    const transaction = createAuth0Transaction(requestUrl.searchParams.get("returnTo") ?? "/");
    const response = NextResponse.redirect(buildAuthorizationUrl(config, transaction));
    response.cookies.set(
      AUTH0_TRANSACTION_COOKIE,
      createSignedCookieValue(transaction, 10 * 60),
      cookieOptions(10 * 60)
    );
    return response;
  } catch (error) {
    const message = error instanceof Error ? error.message : "Auth0 login could not start";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

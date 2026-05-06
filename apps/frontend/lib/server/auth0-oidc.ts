import {
  createHash,
  createPublicKey,
  randomBytes,
  verify as verifySignature
} from "node:crypto";
import type { JsonWebKey as NodeJsonWebKey } from "node:crypto";
import type { Auth0UserSession } from "@/lib/auth0-config";
import { loadAuth0UserSession } from "@/lib/server/supervisor";

export type Auth0Transaction = {
  state: string;
  nonce: string;
  codeVerifier: string;
  returnTo: string;
};

type Auth0UserAuthConfig = {
  domain: string;
  issuer: string;
  authorizationEndpoint: string;
  tokenEndpoint: string;
  jwksEndpoint: string;
  clientId: string;
  audience: string;
  scope: string;
  callbackUrl: string;
  appBaseUrl: string;
};

type Auth0TokenResponse = {
  access_token?: string;
  id_token?: string;
  token_type?: string;
  expires_in?: number;
  scope?: string;
};

type JwtHeader = {
  alg?: string;
  kid?: string;
  typ?: string;
};

type JwtClaims = Record<string, unknown> & {
  aud?: string | string[];
  email?: string;
  exp?: number;
  iss?: string;
  name?: string;
  nickname?: string;
  nonce?: string;
  permissions?: string[];
  scope?: string;
  sub?: string;
};

type Auth0Jwk = NodeJsonWebKey & {
  kid?: string;
};

type JwksResponse = {
  keys?: Auth0Jwk[];
};

export function getAuth0UserAuthConfig(requestUrl: URL): Auth0UserAuthConfig {
  const domain = normalizeDomain(requiredEnv("AUTH0_DOMAIN"));
  const appBaseUrl = normalizeBaseUrl(
    process.env.AUTH0_APP_BASE_URL || `${requestUrl.protocol}//${requestUrl.host}`
  );
  const callbackUrl = process.env.AUTH0_CALLBACK_URL || `${appBaseUrl}/api/auth/callback`;
  const scope = normalizeScope(process.env.AUTH0_USER_SCOPE || "openid profile email");

  return {
    domain,
    issuer: `https://${domain}/`,
    authorizationEndpoint: `https://${domain}/authorize`,
    tokenEndpoint: `https://${domain}/oauth/token`,
    jwksEndpoint: `https://${domain}/.well-known/jwks.json`,
    clientId: requiredEnv("AUTH0_USER_CLIENT_ID"),
    audience: requiredEnv("AUTH0_AUDIENCE"),
    scope,
    callbackUrl,
    appBaseUrl
  };
}

export function createAuth0Transaction(returnTo = "/"): Auth0Transaction {
  return {
    state: randomToken(),
    nonce: randomToken(),
    codeVerifier: randomToken(48),
    returnTo: returnTo.startsWith("/") ? returnTo : "/"
  };
}

export function buildAuthorizationUrl(
  config: Auth0UserAuthConfig,
  transaction: Auth0Transaction
): URL {
  const url = new URL(config.authorizationEndpoint);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", config.clientId);
  url.searchParams.set("redirect_uri", config.callbackUrl);
  url.searchParams.set("scope", config.scope);
  url.searchParams.set("audience", config.audience);
  url.searchParams.set("state", transaction.state);
  url.searchParams.set("nonce", transaction.nonce);
  url.searchParams.set("code_challenge", pkceChallenge(transaction.codeVerifier));
  url.searchParams.set("code_challenge_method", "S256");
  return url;
}

export async function exchangeCodeForSession(
  config: Auth0UserAuthConfig,
  transaction: Auth0Transaction,
  code: string,
  sessionId: string
): Promise<Auth0UserSession> {
  const tokenResponse = await exchangeAuthorizationCode(config, transaction, code);
  const accessToken = requiredTokenValue(tokenResponse.access_token, "access_token");
  const idToken = requiredTokenValue(tokenResponse.id_token, "id_token");
  if (tokenResponse.token_type?.toLowerCase() !== "bearer") {
    throw new Error("Auth0 token response returned an unsupported token type");
  }

  const idClaims = await verifyJwt(idToken, {
    audience: config.clientId,
    issuer: config.issuer,
    jwksEndpoint: config.jwksEndpoint,
    nonce: transaction.nonce
  });
  const accessClaims = await verifyJwt(accessToken, {
    audience: config.audience,
    issuer: config.issuer,
    jwksEndpoint: config.jwksEndpoint
  });

  if (!idClaims.sub) throw new Error("Auth0 ID token is missing a subject");
  const tokenRef = `auth0:${createHash("sha256").update(accessToken).digest("hex").slice(0, 16)}`;
  const expiresIn =
    typeof tokenResponse.expires_in === "number" && tokenResponse.expires_in > 0
      ? tokenResponse.expires_in
      : null;

  const session = await loadAuth0UserSession({
    audience: config.audience,
    expiresAt: expiresIn ? Date.now() + expiresIn * 1000 : null,
    sessionId,
    tokenRef,
    tokenScopes: collectScopes(tokenResponse, accessClaims),
    userEmail: idClaims.email ?? null,
    userId: idClaims.sub,
    userName: idClaims.name ?? idClaims.nickname ?? null
  });
  return {
    ...session,
    authContextRef: accessToken
  };
}

export function sessionMaxAgeSeconds(session: Auth0UserSession): number {
  if (!session.expiresAt) return 3600;
  return Math.max(60, Math.min(8 * 60 * 60, Math.floor((session.expiresAt - Date.now()) / 1000)));
}

export function auth0ErrorRedirect(config: Auth0UserAuthConfig, detail: string): URL {
  const url = new URL(config.appBaseUrl);
  url.searchParams.set("auth0_error", detail);
  return url;
}

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value || !value.trim()) {
    throw new Error(`${name} is required for Auth0 user login`);
  }
  return value.trim();
}

function normalizeDomain(domain: string): string {
  return domain.replace(/^https?:\/\//, "").replace(/\/+$/, "");
}

function normalizeBaseUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

function normalizeScope(scope: string): string {
  const scopes = new Set(scope.split(/\s+/).filter(Boolean));
  scopes.add("openid");
  return [...scopes].sort().join(" ");
}

async function exchangeAuthorizationCode(
  config: Auth0UserAuthConfig,
  transaction: Auth0Transaction,
  code: string
): Promise<Auth0TokenResponse> {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: config.clientId,
    code,
    code_verifier: transaction.codeVerifier,
    redirect_uri: config.callbackUrl
  });

  const response = await fetch(config.tokenEndpoint, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
    cache: "no-store"
  });
  const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    throw new Error(auth0ResponseDetail(response.status, payload));
  }
  return payload as Auth0TokenResponse;
}

function requiredTokenValue(value: string | undefined, key: string): string {
  if (!value) throw new Error(`Auth0 token response is missing ${key}`);
  return value;
}

async function verifyJwt(
  token: string,
  expected: {
    audience: string;
    issuer: string;
    jwksEndpoint: string;
    nonce?: string;
  }
): Promise<JwtClaims> {
  const [encodedHeader, encodedPayload, encodedSignature, extra] = token.split(".");
  if (!encodedHeader || !encodedPayload || !encodedSignature || extra) {
    throw new Error("Auth0 token is not a compact JWT");
  }

  const header = JSON.parse(base64UrlDecode(encodedHeader).toString("utf8")) as JwtHeader;
  const claims = JSON.parse(base64UrlDecode(encodedPayload).toString("utf8")) as JwtClaims;
  if (header.alg !== "RS256" || !header.kid) {
    throw new Error("Auth0 token uses an unsupported signing key");
  }

  const key = await publicKeyForJwt(expected.jwksEndpoint, header.kid);
  const valid = verifySignature(
    "RSA-SHA256",
    Buffer.from(`${encodedHeader}.${encodedPayload}`),
    key,
    base64UrlDecode(encodedSignature)
  );
  if (!valid) throw new Error("Auth0 token signature validation failed");

  const now = Math.floor(Date.now() / 1000);
  if (claims.iss !== expected.issuer) throw new Error("Auth0 token issuer validation failed");
  if (!audienceMatches(claims.aud, expected.audience)) {
    throw new Error("Auth0 token audience validation failed");
  }
  if (typeof claims.exp !== "number" || claims.exp + 60 < now) {
    throw new Error("Auth0 token is expired");
  }
  if (expected.nonce && claims.nonce !== expected.nonce) {
    throw new Error("Auth0 token nonce validation failed");
  }
  return claims;
}

async function publicKeyForJwt(jwksEndpoint: string, kid: string) {
  const response = await fetch(jwksEndpoint, { cache: "no-store" });
  const jwks = (await response.json().catch(() => ({}))) as JwksResponse;
  if (!response.ok || !Array.isArray(jwks.keys)) {
    throw new Error("Auth0 JWKS fetch failed");
  }
  const jwk = jwks.keys.find((candidate) => candidate.kid === kid);
  if (!jwk) throw new Error("Auth0 signing key was not found");
  return createPublicKey({ key: jwk, format: "jwk" });
}

function audienceMatches(actual: string | string[] | undefined, expected: string): boolean {
  return Array.isArray(actual) ? actual.includes(expected) : actual === expected;
}

function collectScopes(tokenResponse: Auth0TokenResponse, accessClaims: JwtClaims): string[] {
  const scopes: string[] = [];
  if (tokenResponse.scope) scopes.push(...tokenResponse.scope.split(/\s+/));
  if (typeof accessClaims.scope === "string") scopes.push(...accessClaims.scope.split(/\s+/));
  if (Array.isArray(accessClaims.permissions)) scopes.push(...accessClaims.permissions);
  return [...new Set(scopes.map((scope) => scope.trim()).filter(Boolean))].sort();
}

function auth0ResponseDetail(status: number, payload: Record<string, unknown>): string {
  const error = typeof payload.error === "string" ? payload.error : null;
  const description =
    typeof payload.error_description === "string" ? payload.error_description : null;
  return [error, description].filter(Boolean).length
    ? `Auth0 user login failed with HTTP ${status}: ${[error, description].filter(Boolean).join(" - ")}`
    : `Auth0 user login failed with HTTP ${status}`;
}

function randomToken(bytes = 32): string {
  return randomBytes(bytes).toString("base64url");
}

function pkceChallenge(verifier: string): string {
  return createHash("sha256").update(verifier).digest("base64url");
}

function base64UrlDecode(value: string): Buffer {
  return Buffer.from(value, "base64url");
}

import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import type { Auth0UserSession } from "@/lib/auth0-config";

export const AUTH0_SESSION_COOKIE = "magnum_opus_auth0_session";
export const AUTH0_TRANSACTION_COOKIE = "magnum_opus_auth0_transaction";

type SignedCookieEnvelope<T> = {
  value: T;
  exp: number;
};

export type CookieOptions = {
  httpOnly: true;
  sameSite: "lax";
  secure: boolean;
  path: "/";
  maxAge: number;
};

export function createSessionId(): string {
  return `auth0-session-${randomBytes(16).toString("hex")}`;
}

export function createSignedCookieValue<T>(value: T, maxAgeSeconds: number): string {
  const envelope: SignedCookieEnvelope<T> = {
    value,
    exp: Math.floor(Date.now() / 1000) + maxAgeSeconds
  };
  const payload = base64UrlEncode(JSON.stringify(envelope));
  return `${payload}.${sign(payload)}`;
}

export function readSignedCookieValue<T>(cookieValue: string | null): T | null {
  if (!cookieValue) return null;

  const [payload, signature, extra] = cookieValue.split(".");
  if (!payload || !signature || extra) return null;
  if (!signaturesMatch(signature, sign(payload))) return null;

  try {
    const envelope = JSON.parse(base64UrlDecode(payload).toString("utf8")) as
      | SignedCookieEnvelope<T>
      | null;
    if (!envelope || typeof envelope !== "object") return null;
    if (typeof envelope.exp !== "number" || envelope.exp < Math.floor(Date.now() / 1000)) {
      return null;
    }
    return envelope.value;
  } catch {
    return null;
  }
}

export function readAuth0SessionCookie(cookieHeader: string | null): Auth0UserSession | null {
  try {
    return readSignedCookieValue<Auth0UserSession>(
      getCookieValue(cookieHeader, AUTH0_SESSION_COOKIE)
    );
  } catch {
    return null;
  }
}

export function cookieOptions(maxAge: number): CookieOptions {
  return {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge
  };
}

export function expiredCookieOptions(): CookieOptions {
  return cookieOptions(0);
}

export function getCookieValue(cookieHeader: string | null, name: string): string | null {
  if (!cookieHeader) return null;
  for (const part of cookieHeader.split(";")) {
    const [rawName, ...rawValue] = part.trim().split("=");
    if (rawName === name) return rawValue.join("=") || null;
  }
  return null;
}

function sign(payload: string): string {
  return createHmac("sha256", sessionSecret()).update(payload).digest("base64url");
}

function signaturesMatch(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

function sessionSecret(): string {
  const secret = process.env.AUTH0_SESSION_SECRET;
  if (!secret || secret.length < 32) {
    throw new Error("AUTH0_SESSION_SECRET must be at least 32 characters");
  }
  return secret;
}

function base64UrlEncode(value: string): string {
  return Buffer.from(value, "utf8").toString("base64url");
}

function base64UrlDecode(value: string): Buffer {
  return Buffer.from(value, "base64url");
}

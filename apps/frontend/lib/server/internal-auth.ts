import { createHmac } from "crypto";
import type { SanitizedSessionContext } from "@/lib/server/supervisor";

export const SESSION_CONTEXT_HEADER = "x-magnum-session-context";
export const SESSION_CONTEXT_SIGNATURE_HEADER = "x-magnum-session-signature";

type TrustedSessionContext = SanitizedSessionContext & {
  correlation_id: string;
  expires_at: string;
};

export function signedSessionContextHeaders(
  context: SanitizedSessionContext,
  correlationId: string
): Record<string, string> {
  const trusted: TrustedSessionContext = {
    ...context,
    correlation_id: correlationId,
    expires_at: new Date(Date.now() + 5 * 60 * 1000).toISOString()
  };
  const encoded = Buffer.from(stableJson(trusted), "utf8").toString("base64url");
  return {
    [SESSION_CONTEXT_HEADER]: encoded,
    [SESSION_CONTEXT_SIGNATURE_HEADER]: createHmac("sha256", internalAuthSecret())
      .update(encoded)
      .digest("hex")
  };
}

export function internalAuthSecret(): string {
  const secret = process.env.INTERNAL_SERVICE_AUTH_SECRET;
  if (!secret) {
    throw new Error("INTERNAL_SERVICE_AUTH_SECRET is required for internal service calls");
  }
  return secret;
}

function stableJson(value: unknown): string {
  return JSON.stringify(sortValue(value));
}

function sortValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map((item) => sortValue(item));
  if (!isRecord(value)) return value;
  return Object.fromEntries(
    Object.keys(value)
      .sort()
      .map((key) => [key, sortValue(value[key])])
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

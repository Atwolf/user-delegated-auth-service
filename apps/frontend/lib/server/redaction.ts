const SENSITIVE_KEYS = new Set([
  "accesstoken",
  "apikey",
  "authcontextref",
  "authorization",
  "bearertoken",
  "clientsecret",
  "credential",
  "idtoken",
  "jwksendpoint",
  "password",
  "privatekey",
  "rawtoken",
  "refreshtoken",
  "secret",
  "sessionid",
  "tenantid",
  "token",
  "tokenendpoint",
  "tokenref",
  "userid"
]);

export function sanitizeBrowserRecord(record: Record<string, unknown>): Record<string, unknown> {
  return sanitizeBrowserValue(record) as Record<string, unknown>;
}

export function sanitizeBrowserValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeBrowserValue(item));
  }

  if (!isRecord(value)) return value;

  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !isSensitiveBrowserKey(key))
      .map(([key, item]) => [key, sanitizeBrowserValue(item)])
  );
}

export function isSensitiveBrowserKey(key: string): boolean {
  const normalized = key.replace(/[^a-z0-9]/gi, "").toLowerCase();
  return (
    SENSITIVE_KEYS.has(normalized) ||
    normalized.endsWith("secret") ||
    normalized.endsWith("token") ||
    normalized.includes("tokenref") ||
    normalized.includes("authorization") ||
    normalized.includes("credential")
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

export const AUTH0_STORAGE_KEY = "magnum-opus.auth0.client-config.v1";

export type Auth0PublicConfig = {
  serverTemplate: "Auth0";
  domain: string;
  tokenEndpoint: string;
  jwksEndpoint: string;
  clientId: string;
  scope: string;
  audience: string;
};

export type Auth0Config = Auth0PublicConfig & {
  clientSecret: string;
};

export type ValidationResult = {
  valid: boolean;
  errors: Partial<Record<keyof Auth0Config, string>>;
};

export const DEFAULT_AUTH0_CONFIG: Auth0PublicConfig = {
  serverTemplate: "Auth0",
  domain: "samples.auth0.com",
  tokenEndpoint: "https://samples.auth0.com/oauth/token",
  jwksEndpoint: "https://samples.auth0.com/.well-known/jwks.json",
  clientId: "",
  scope: "openid profile email",
  audience: ""
};

export function normalizeAuth0Domain(domain: string): string {
  return domain.trim().replace(/^https?:\/\//, "").replace(/\/+$/, "");
}

export function deriveAuth0Endpoints(domain: string) {
  const normalized = normalizeAuth0Domain(domain);
  const base = `https://${normalized}`;
  return {
    tokenEndpoint: `${base}/oauth/token`,
    jwksEndpoint: `${base}/.well-known/jwks.json`
  };
}

export function toPublicConfig(config: Auth0Config): Auth0PublicConfig {
  return {
    serverTemplate: config.serverTemplate,
    domain: config.domain,
    tokenEndpoint: config.tokenEndpoint,
    jwksEndpoint: config.jwksEndpoint,
    clientId: config.clientId,
    scope: config.scope,
    audience: config.audience
  };
}

export function loadPublicConfig(storage: Pick<Storage, "getItem">): Auth0PublicConfig {
  const raw = storage.getItem(AUTH0_STORAGE_KEY);
  if (!raw) return DEFAULT_AUTH0_CONFIG;

  try {
    const parsed = JSON.parse(raw) as Partial<Auth0PublicConfig>;
    return {
      ...DEFAULT_AUTH0_CONFIG,
      ...parsed,
      serverTemplate: "Auth0"
    };
  } catch {
    return DEFAULT_AUTH0_CONFIG;
  }
}

export function savePublicConfig(
  storage: Pick<Storage, "setItem">,
  config: Auth0PublicConfig
) {
  storage.setItem(AUTH0_STORAGE_KEY, JSON.stringify(config));
}

export function clearPublicConfig(storage: Pick<Storage, "removeItem">) {
  storage.removeItem(AUTH0_STORAGE_KEY);
}

export function encodeAuth0ConfigHeader(config: Auth0Config): string {
  const json = JSON.stringify(config);
  if (typeof window === "undefined") {
    return Buffer.from(json, "utf8").toString("base64url");
  }

  const bytes = new TextEncoder().encode(json);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return window
    .btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

export function decodeAuth0ConfigHeader(header: string | null): Auth0Config | null {
  if (!header) return null;
  try {
    const decoded = Buffer.from(header, "base64url").toString("utf8");
    return JSON.parse(decoded) as Auth0Config;
  } catch {
    return null;
  }
}

export function validateAuth0Config(config: Auth0Config): ValidationResult {
  const errors: ValidationResult["errors"] = {};
  const domain = normalizeAuth0Domain(config.domain);

  if (!domain) errors.domain = "Auth0 domain is required.";
  if (!config.tokenEndpoint.startsWith("http")) {
    errors.tokenEndpoint = "Token endpoint must be an HTTP URL.";
  }
  if (!config.jwksEndpoint.startsWith("http")) {
    errors.jwksEndpoint = "JWKS endpoint must be an HTTP URL.";
  }
  if (!config.clientId.trim()) errors.clientId = "Client ID is required.";
  if (!config.clientSecret.trim()) errors.clientSecret = "Client secret is required.";
  if (!config.scope.trim()) errors.scope = "At least one scope is required.";

  return {
    valid: Object.keys(errors).length === 0,
    errors
  };
}

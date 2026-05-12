export type Auth0UserPersona = {
  displayName: string;
  headline: string;
  greeting: string;
  traits: string[];
};

export type Auth0UserSession = {
  sessionId: string;
  tokenRef: string;
  scope: string;
  audience: string | null;
  expiresAt: number | null;
  tenantId?: string | null;
  userId: string;
  userEmail: string | null;
  allowedTools: string[];
  persona: Auth0UserPersona;
};

export type Auth0BrowserSession = Omit<Auth0UserSession, "tokenRef">;

export type Auth0ServerSession = Auth0UserSession & {
  authContextRef: string;
};

export function parseScopeString(scope: string): string[] {
  return [...new Set(scope.split(/\s+/).map((item) => item.trim()).filter(Boolean))].sort();
}

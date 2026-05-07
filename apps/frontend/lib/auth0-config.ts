export type Auth0UserPersona = {
  displayName: string;
  headline: string;
  greeting: string;
  traits: string[];
};

export type Auth0UserSession = {
  sessionId: string;
  tokenRef: string;
  authContextRef?: string;
  scope: string;
  audience: string | null;
  expiresAt: number | null;
  userId: string;
  userEmail: string | null;
  allowedTools: string[];
  persona: Auth0UserPersona;
};

export function parseScopeString(scope: string): string[] {
  return [...new Set(scope.split(/\s+/).map((item) => item.trim()).filter(Boolean))].sort();
}

import type { Auth0UserSession } from "@/lib/auth0-config";

const sessions = new Map<string, Auth0UserSession>();

export function storeAuth0Session(session: Auth0UserSession): void {
  sessions.set(session.sessionId, session);
}

export function loadAuth0Session(sessionId: string): Auth0UserSession | null {
  return sessions.get(sessionId) ?? null;
}

export function deleteAuth0Session(sessionId: string): void {
  sessions.delete(sessionId);
}

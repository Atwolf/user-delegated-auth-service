import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createAuth0SessionCookieValue,
  readAuth0SessionCookieValue,
  readSignedCookieValue
} from "@/lib/server/auth0-session";

const session = {
  sessionId: "auth0-session-cookie-test",
  tokenRef: "auth0:sample",
  authContextRef: "raw-auth0-access-token",
  scope: "read:apps read:users",
  audience: "https://api.example.test",
  expiresAt: Date.now() + 3600_000,
  userId: "auth0|user-1",
  userEmail: "sample@example.com",
  allowedTools: ["inspect_vm"],
  persona: {
    displayName: "sample",
    headline: "sample is cleared for workflow tools.",
    greeting: "Welcome back, sample.",
    traits: ["email: sample@example.com"]
  }
};

describe("Auth0 session cookie", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("stores only a server-side session handle in the browser cookie", () => {
    vi.stubEnv("AUTH0_SESSION_SECRET", "01234567890123456789012345678901");

    const cookie = createAuth0SessionCookieValue(session, 3600);
    const handle = readSignedCookieValue<Record<string, unknown>>(cookie);

    expect(handle).toEqual({ sessionId: session.sessionId });
    expect(JSON.stringify(handle)).not.toContain("tokenRef");
    expect(JSON.stringify(handle)).not.toContain("authContextRef");
    expect(JSON.stringify(handle)).not.toContain("raw-auth0-access-token");
    expect(readAuth0SessionCookieValue(cookie)).toMatchObject({
      authContextRef: "raw-auth0-access-token",
      tokenRef: "auth0:sample",
      userId: "auth0|user-1"
    });
  });
});

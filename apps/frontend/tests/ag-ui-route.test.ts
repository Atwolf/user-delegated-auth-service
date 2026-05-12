import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "@/app/api/ag-ui/route";
import {
  AUTH0_SESSION_COOKIE,
  createAuth0SessionCookieValue
} from "@/lib/server/auth0-session";

const session = {
  sessionId: "auth0-session-1",
  tokenRef: "auth0:sample",
  authContextRef: "raw-auth0-access-token",
  scope: "read:apps read:users read:apps",
  audience: "https://api.example.test",
  expiresAt: Date.now() + 3600_000,
  userId: "auth0|user-1",
  userEmail: "sample@example.com",
  allowedTools: ["inspect_vm", "inspect_dns_record", "inspect_vm"],
  persona: {
    displayName: "sample",
    headline: "sample is cleared for workflow tools.",
    greeting: "Welcome back, sample.",
    traits: ["email: sample@example.com"]
  }
};

describe("AG-UI proxy route", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("requires a signed Auth0 session cookie", async () => {
    const response = await POST(new Request("http://localhost/api/ag-ui", { method: "POST" }));

    expect(response.status).toBe(401);
  });

  it("injects sanitized session context before forwarding", async () => {
    vi.stubEnv("AUTH0_SESSION_SECRET", "01234567890123456789012345678901");
    vi.stubEnv("INTERNAL_SERVICE_AUTH_SECRET", "01234567890123456789012345678901");
    vi.stubEnv("AG_UI_GATEWAY_URL", "http://ag-ui.test/agent");
    const fetchMock = vi.fn(async () => new Response("event: RUN_FINISHED\n\n"));
    vi.stubGlobal("fetch", fetchMock);

    const cookie = createAuth0SessionCookieValue(session, 3600);
    const response = await POST(
      new Request("http://localhost/api/ag-ui", {
        method: "POST",
        headers: {
          cookie: `${AUTH0_SESSION_COOKIE}=${cookie}`,
          "content-type": "application/json"
        },
        body: JSON.stringify({
          threadId: "thread-1",
          runId: "run-1",
          messages: [{ role: "user", content: "Check VM" }],
          access_token: "browser-access-token",
          accessToken: "browser-access-token-camel",
          bearerToken: "browser-bearer-token",
          clientSecret: "browser-client-secret-camel",
          context: [],
          forwardedProps: {},
          rawToken: "browser-raw-token",
          state: {
            auth_context_ref: "browser-auth-context",
            authContextRef: "browser-auth-context-camel",
            client_secret: "browser-client-secret",
            credential: "browser-credential",
            idToken: "browser-id-token-camel",
            nested: { authorization: "Bearer browser-token" },
            refreshToken: "browser-refresh-token-camel",
            tenant_id: "tenant-1"
          },
          tools: []
        })
      })
    );

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://ag-ui.test/agent",
      expect.objectContaining({
        headers: expect.objectContaining({
          "x-magnum-session-context": expect.any(String),
          "x-magnum-session-signature": expect.any(String)
        })
      })
    );
    const body = String(fetchMock.mock.calls[0]?.[1]?.body);
    expect(JSON.parse(body)).toEqual({
      messages: [{ role: "user", content: "Check VM" }],
      runId: "run-1",
      state: { nested: {} },
      threadId: "thread-1"
    });
    expect(body).toContain('"state":{"nested":{}}');
    expect(body).not.toContain('"allowed_tools"');
    expect(body).not.toContain('"token_scopes"');
    expect(body).not.toContain('"tenant_id"');
    expect(body).not.toContain('"user_id"');
    expect(body).not.toContain("auth0|user-1");
    expect(body).not.toContain("auth0:sample");
    expect(body).not.toContain("auth_context_ref");
    expect(body).not.toContain("access_token");
    expect(body).not.toContain("authorization");
    expect(body).not.toContain("browser-auth-context");
    expect(body).not.toContain("browser-auth-context-camel");
    expect(body).not.toContain("browser-access-token");
    expect(body).not.toContain("browser-access-token-camel");
    expect(body).not.toContain("browser-bearer-token");
    expect(body).not.toContain("browser-client-secret");
    expect(body).not.toContain("browser-client-secret-camel");
    expect(body).not.toContain("browser-credential");
    expect(body).not.toContain("browser-id-token-camel");
    expect(body).not.toContain("browser-raw-token");
    expect(body).not.toContain("browser-refresh-token-camel");
    expect(body).not.toContain("raw-auth0-access-token");
    expect(body).not.toContain("client_secret");
    expect(body).not.toContain("clientSecret");
    expect(body).not.toContain("context");
    expect(body).not.toContain("forwardedProps");
    expect(body).not.toContain("tools");
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createAgentThread,
  loadAuth0UserSession,
  restoreAgentThread,
  sanitizedSessionContext
} from "@/lib/server/supervisor";
import { internalAuthSecret } from "@/lib/server/internal-auth";

const AUTH0_SESSION = {
  sessionId: "auth0-session-1",
  tokenRef: "auth0:sample",
  scope: "read:users read:apps",
  audience: "https://api.example.test",
  expiresAt: Date.now() + 3600_000,
  userId: "auth0|user-1",
  userEmail: "sample@example.com",
  allowedTools: ["get_identity_profile", "get_developer_app"],
  persona: {
    displayName: "sample",
    headline: "sample is cleared for 2 workflow tools.",
    greeting: "Welcome back, sample.",
    traits: ["email: sample@example.com"]
  }
};

describe("supervisor client", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("loads Auth0 session metadata without sending user credentials", async () => {
    vi.stubEnv("SUPERVISOR_BASE_URL", "http://supervisor.test");
    vi.stubEnv("INTERNAL_SERVICE_AUTH_SECRET", "01234567890123456789012345678901");
    const fetchMock = vi.fn(async () =>
      Response.json({
        scope: "read:users read:apps",
        audience: "https://api.example.test",
        token_ref: "auth0:sample",
        user_id: "auth0|user-1",
        user_email: "sample@example.com",
        allowed_tools: ["get_identity_profile", "get_developer_app"],
        persona: {
          display_name: "sample",
          headline: "sample is cleared for 2 workflow tools.",
          greeting: "Welcome back, sample.",
          traits: ["email: sample@example.com"]
        }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const session = await loadAuth0UserSession({
      audience: "https://api.example.test",
      expiresAt: Date.now() + 3600_000,
      sessionId: "auth0-session-1",
      tokenRef: "auth0:sample",
      tokenScopes: ["read:apps", "read:users"],
      tenantId: "tenant-1",
      userEmail: "sample@example.com",
      userId: "auth0|user-1",
      userName: "sample"
    });

    expect(session.tokenRef).toBe("auth0:sample");
    expect(session.tenantId).toBe("tenant-1");
    expect(session.allowedTools).toEqual(["get_identity_profile", "get_developer_app"]);
    expect(session.persona.displayName).toBe("sample");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://supervisor.test/identity/auth0/session",
      expect.objectContaining({
        headers: expect.objectContaining({
          "content-type": "application/json",
          "x-magnum-session-context": expect.any(String),
          "x-magnum-session-signature": expect.any(String)
        }),
        body: expect.stringContaining('"user_id":"auth0|user-1"')
      })
    );
    const body = String(fetchMock.mock.calls[0]?.[1]?.body);
    expect(body).toContain('"tenant_id":"tenant-1"');
    expect(body).not.toContain("password");
    expect(body).not.toContain("client_secret");
  });

  it("builds a sanitized session context without raw auth references", () => {
    const context = sanitizedSessionContext({
      ...AUTH0_SESSION,
      scope: "read:apps read:users read:apps",
      allowedTools: ["get_identity_profile", "get_developer_app", "get_identity_profile"]
    });

    expect(context).toEqual({
      allowed_tools: ["get_developer_app", "get_identity_profile"],
      session_id: "auth0-session-1",
      token_ref: "auth0:sample",
      token_scopes: ["read:apps", "read:users"],
      user_id: "auth0|user-1"
    });
    expect(JSON.stringify(context)).not.toContain("raw-auth0-access-token");
  });

  it("materializes tenant id into trusted session context when present", () => {
    const context = sanitizedSessionContext({
      ...AUTH0_SESSION,
      tenantId: "tenant-1"
    });

    expect(context.tenant_id).toBe("tenant-1");
  });

  it("requires a dedicated internal service auth secret", () => {
    vi.stubEnv("AUTH0_SESSION_SECRET", "01234567890123456789012345678901");
    vi.stubEnv("INTERNAL_SERVICE_AUTH_SECRET", "");

    expect(() => internalAuthSecret()).toThrow("INTERNAL_SERVICE_AUTH_SECRET is required");
  });

  it("creates Agent Service threads with sanitized session context", async () => {
    vi.stubEnv("AGENT_SERVICE_URL", "http://agent-service.test");
    vi.stubEnv("INTERNAL_SERVICE_AUTH_SECRET", "01234567890123456789012345678901");
    const fetchMock = vi.fn(async () =>
      Response.json({
        messages: [
          { role: "user", content: "Check VM" },
          { role: "tool", content: "internal tool transcript" },
          { role: "assistant", content: "VM looks healthy." }
        ],
        state: {
          accessToken: "response-access-token",
          authContextRef: "response-auth-context",
          nested: { clientSecret: "response-client-secret", ready: true },
          ready: true
        },
        thread_id: "thread-123",
        title: "Ops"
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const thread = await createAgentThread({
      ...AUTH0_SESSION,
      scope: "read:apps read:users read:apps",
      allowedTools: ["get_identity_profile", "get_developer_app", "get_identity_profile"]
    });

    expect(thread.threadId).toBe("thread-123");
    expect(thread.messages).toEqual([
      { role: "user", content: "Check VM" },
      { role: "assistant", content: "VM looks healthy." }
    ]);
    expect(thread.state).toEqual({ nested: { ready: true }, ready: true });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://agent-service.test/threads",
      expect.objectContaining({
        body: expect.stringContaining('"user_id":"auth0|user-1"')
      })
    );
    const body = String(fetchMock.mock.calls[0]?.[1]?.body);
    expect(body).toContain('"user_id":"auth0|user-1"');
    expect(body).toContain('"token_scopes":["read:apps","read:users"]');
    expect(body).toContain('"allowed_tools":["get_developer_app","get_identity_profile"]');
    expect(body).toContain('"state":{}');
    expect(body).not.toContain("auth_context_ref");
    expect(body).not.toContain("raw-auth0-access-token");
  });

  it("uses shared HTTP error handling", async () => {
    vi.stubEnv("AGENT_SERVICE_URL", "http://agent-service.test");
    vi.stubEnv("INTERNAL_SERVICE_AUTH_SECRET", "01234567890123456789012345678901");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        expect(String(input)).toBe("http://agent-service.test/threads/thread-404");
        expect(init?.method).toBe("GET");
        return Response.json({ detail: "thread is not available" }, { status: 404 });
      })
    );

    await expect(restoreAgentThread("thread-404", AUTH0_SESSION)).rejects.toThrow(
      "Thread restore failed with HTTP 404: thread is not available"
    );
  });
});

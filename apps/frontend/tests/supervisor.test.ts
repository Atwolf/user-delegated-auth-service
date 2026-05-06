import { afterEach, describe, expect, it, vi } from "vitest";
import { approveWorkflow, loadAuth0UserSession, planWorkflow } from "@/lib/server/supervisor";

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
      userEmail: "sample@example.com",
      userId: "auth0|user-1",
      userName: "sample"
    });

    expect(session.tokenRef).toBe("auth0:sample");
    expect(session.allowedTools).toEqual(["get_identity_profile", "get_developer_app"]);
    expect(session.persona.displayName).toBe("sample");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://supervisor.test/identity/auth0/session",
      expect.objectContaining({
        body: expect.stringContaining('"user_id":"auth0|user-1"')
      })
    );
    const body = String(fetchMock.mock.calls[0]?.[1]?.body);
    expect(body).not.toContain("password");
    expect(body).not.toContain("client_secret");
  });

  it("sends Auth0-issued token scopes and allowed tools to workflow planning", async () => {
    vi.stubEnv("AGENT_SERVICE_URL", "http://agent-service.test");
    const fetchMock = vi.fn(async () =>
      Response.json({
        workflow_id: "wf-123",
        status: { status: "awaiting_approval" },
        plan_hash: "sha256:abc",
        authorization: { workflow_id: "wf-123", scopes: ["read:apps"], proposals: [] },
        plan: {
          workflow_id: "wf-123",
          user_id: "sample-user",
          session_id: "sample-session",
          created_at: new Date().toISOString(),
          steps: []
        },
        events: [],
        step_results: []
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await planWorkflow("Check app", {
      ...AUTH0_SESSION,
      scope: "read:apps read:users read:apps",
      allowedTools: ["get_identity_profile", "get_developer_app", "get_identity_profile"]
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://agent-service.test/workflows/plan",
      expect.objectContaining({
        body: expect.stringContaining('"user_id":"auth0|user-1"')
      })
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "http://agent-service.test/workflows/plan",
      expect.objectContaining({
        body: expect.stringContaining('"token_scopes":["read:apps","read:users"]')
      })
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "http://agent-service.test/workflows/plan",
      expect.objectContaining({
        body: expect.stringContaining(
          '"allowed_tools":["get_developer_app","get_identity_profile"]'
        )
      })
    );
  });

  it("uses shared HTTP error handling", async () => {
    vi.stubEnv("AGENT_SERVICE_URL", "http://agent-service.test");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ detail: "plan_hash does not match" }, { status: 409 }))
    );

    await expect(approveWorkflow("wf-1", "sha256:abc", AUTH0_SESSION)).rejects.toThrow(
      "Workflow approval failed with HTTP 409: plan_hash does not match"
    );
  });
});

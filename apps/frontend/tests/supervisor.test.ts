import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_AUTH0_CONFIG } from "@/lib/auth0-config";
import { approveWorkflow, exchangeClientCredentials, planWorkflow } from "@/lib/server/supervisor";

const AUTH0_CONFIG = {
  ...DEFAULT_AUTH0_CONFIG,
  clientId: "client-id",
  clientSecret: "client-secret"
};

describe("supervisor client", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("posts Auth0 config to the supervisor without mock branches", async () => {
    vi.stubEnv("SUPERVISOR_BASE_URL", "http://supervisor.test");
    const fetchMock = vi.fn(async () =>
      Response.json({
        access_token: "issued-access-token",
        token_type: "Bearer",
        expires_in: 3600,
        scope: "read:users read:apps",
        audience: "https://api.example.test",
        token_ref: "auth0:sample"
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const token = await exchangeClientCredentials(AUTH0_CONFIG);

    expect(token.token_ref).toBe("auth0:sample");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://supervisor.test/identity/client-credentials/token",
      expect.objectContaining({
        body: expect.stringContaining('"client_id":"client-id"')
      })
    );
  });

  it("sends Auth0-issued token scopes to workflow planning", async () => {
    vi.stubEnv("SUPERVISOR_BASE_URL", "http://supervisor.test");
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

    await planWorkflow("Check app", "auth0:sample", "read:apps read:users read:apps");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://supervisor.test/workflows/plan",
      expect.objectContaining({
        body: expect.stringContaining('"token_scopes":["read:apps","read:users"]')
      })
    );
  });

  it("uses shared HTTP error handling", async () => {
    vi.stubEnv("SUPERVISOR_BASE_URL", "http://supervisor.test");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ detail: "plan_hash does not match" }, { status: 409 }))
    );

    await expect(approveWorkflow("wf-1", "sha256:abc")).rejects.toThrow(
      "Workflow approval failed with HTTP 409: plan_hash does not match"
    );
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_AUTH0_CONFIG } from "@/lib/auth0-config";
import { approveWorkflow, exchangeClientCredentials } from "@/lib/server/supervisor";

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

  it("preserves mock supervisor token behavior", async () => {
    vi.stubEnv("SUPERVISOR_BASE_URL", "mock");

    const token = await exchangeClientCredentials(AUTH0_CONFIG);

    expect(token.access_token).toBe("mock-access-token");
    expect(token.token_ref).toBe("auth0:mock");
  });

  it("uses shared HTTP error handling", async () => {
    vi.stubEnv("SUPERVISOR_BASE_URL", "http://supervisor.test");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 409 })));

    await expect(approveWorkflow("wf-1", "sha256:abc")).rejects.toThrow(
      "Workflow approval failed with HTTP 409"
    );
  });
});

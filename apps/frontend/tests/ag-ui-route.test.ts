import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "@/app/api/ag-ui/route";
import {
  AUTH0_SESSION_COOKIE,
  createSignedCookieValue
} from "@/lib/server/auth0-session";

const session = {
  sessionId: "auth0-session-1",
  tokenRef: "auth0:sample",
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
    vi.stubEnv("AG_UI_GATEWAY_URL", "http://ag-ui.test/agent");
    const fetchMock = vi.fn(async () => new Response("event: RUN_FINISHED\n\n"));
    vi.stubGlobal("fetch", fetchMock);

    const cookie = createSignedCookieValue(session, 3600);
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
          state: { tenant_id: "tenant-1" }
        })
      })
    );

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://ag-ui.test/agent",
      expect.objectContaining({
        body: expect.stringContaining('"user_id":"auth0|user-1"')
      })
    );
    const body = String(fetchMock.mock.calls[0]?.[1]?.body);
    expect(body).toContain('"allowed_tools":["inspect_dns_record","inspect_vm"]');
    expect(body).toContain('"token_scopes":["read:apps","read:users"]');
    expect(body).not.toContain("access_token");
    expect(body).not.toContain("client_secret");
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "@/app/api/chat/route";
import { DEFAULT_AUTH0_CONFIG, encodeAuth0ConfigHeader } from "@/lib/auth0-config";

describe("chat route", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("exchanges client credentials and plans a workflow with mocked supervisor responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/identity/client-credentials/token")) {
          return Response.json({
            access_token: "issued-access-token",
            token_type: "Bearer",
            expires_in: 3600,
            scope: "openid profile",
            audience: null,
            token_ref: "auth0:sample"
          });
        }
        if (url.endsWith("/workflows/plan")) {
          return Response.json({
            workflow_id: "wf-123",
            status: { status: "awaiting_approval" },
            plan_hash: "sha256:abc",
            authorization: { workflow_id: "wf-123", scopes: [], proposals: [] },
            plan: {
              workflow_id: "wf-123",
              user_id: "sample-user",
              session_id: "sample-session",
              created_at: new Date().toISOString(),
              steps: []
            },
            events: [],
            step_results: []
          });
        }
        return Response.json({}, { status: 404 });
      })
    );

    const header = encodeAuth0ConfigHeader({
      ...DEFAULT_AUTH0_CONFIG,
      clientId: "client-id",
      clientSecret: "client-secret"
    });
    const response = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-auth0-config": header
        },
        body: JSON.stringify({
          messages: [
            {
              id: "message-1",
              role: "user",
              parts: [{ type: "text", text: "Check user sample-user" }]
            }
          ]
        })
      })
    );

    const body = await response.text();
    expect(body).toContain("Workflow wf-123 is awaiting approval.");
    expect(body).not.toContain("client-secret");
    expect(body).not.toContain("issued-access-token");
  });
});

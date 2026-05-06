import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "@/app/api/chat/route";
import {
  AUTH0_SESSION_COOKIE,
  createSignedCookieValue
} from "@/lib/server/auth0-session";

describe("chat route", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("plans a workflow from an active Auth0 user session", async () => {
    vi.stubEnv("AUTH0_SESSION_SECRET", "x".repeat(32));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/workflows/plan")) {
          expect(JSON.parse(String(init?.body))).toMatchObject({
            allowed_tools: ["get_developer_app", "get_identity_profile"]
          });
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

    const cookieValue = createSignedCookieValue(
      {
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
      },
      3600
    );
    const response = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          cookie: `${AUTH0_SESSION_COOKIE}=${cookieValue}`
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
    expect(body).not.toContain("password");
    expect(body).not.toContain("issued-access-token");
  });

  it("does not describe a ready workflow as HITL-bound", async () => {
    vi.stubEnv("AUTH0_SESSION_SECRET", "x".repeat(32));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/workflows/plan")) {
          expect(JSON.parse(String(init?.body))).toMatchObject({
            auth_context_ref: "auth0-access-token"
          });
          return Response.json({
            workflow: {
              workflow_id: "wf-ready",
              status: "ready",
              plan_hash: "sha256:def",
              policy: { required_scopes: ["read:dns:app.example.com"] },
              tool_intents: [],
              proposal: {
                workflow_id: "wf-ready",
                user_id: "sample-user",
                session_id: "sample-session",
                created_at: new Date().toISOString(),
                steps: []
              },
              created_at: new Date().toISOString()
            }
          });
        }
        return Response.json({}, { status: 404 });
      })
    );

    const cookieValue = createSignedCookieValue(
      {
        sessionId: "auth0-session-1",
        tokenRef: "auth0:sample",
        authContextRef: "auth0-access-token",
        scope: "read:users read:apps",
        audience: "https://api.example.test",
        expiresAt: Date.now() + 3600_000,
        userId: "auth0|user-1",
        userEmail: "sample@example.com",
        allowedTools: ["inspect_dns_record"],
        persona: {
          displayName: "sample",
          headline: "sample is cleared for 1 workflow tool.",
          greeting: "Welcome back, sample.",
          traits: ["email: sample@example.com"]
        }
      },
      3600
    );
    const response = await POST(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          cookie: `${AUTH0_SESSION_COOKIE}=${cookieValue}`
        },
        body: JSON.stringify({
          messages: [
            {
              id: "message-1",
              role: "user",
              parts: [{ type: "text", text: "Inspect DNS" }]
            }
          ]
        })
      })
    );

    const body = await response.text();
    expect(body).toContain("Workflow wf-ready is ready; no HITL approval is required.");
    expect(body).not.toContain("Workflow wf-ready is awaiting approval.");
  });
});

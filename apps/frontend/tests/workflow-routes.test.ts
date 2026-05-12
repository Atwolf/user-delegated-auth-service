import { afterEach, describe, expect, it, vi } from "vitest";
import { POST as approveWorkflow } from "@/app/api/workflows/[workflowId]/approve/route";
import { GET as restoreWorkflow } from "@/app/api/workflows/[workflowId]/route";
import {
  AUTH0_SESSION_COOKIE,
  createAuth0SessionCookieValue
} from "@/lib/server/auth0-session";

const session = {
  sessionId: "auth0-session-1",
  tokenRef: "auth0:sample",
  authContextRef: "raw-auth0-access-token",
  scope: "write:vm write:vm",
  audience: "https://api.example.test",
  expiresAt: Date.now() + 3600_000,
  userId: "auth0|user-1",
  userEmail: "sample@example.com",
  allowedTools: ["restart_vm"],
  persona: {
    displayName: "sample",
    headline: "sample is cleared for workflow tools.",
    greeting: "Welcome back, sample.",
    traits: ["email: sample@example.com"]
  }
};

describe("workflow proxy routes", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("requires a signed Auth0 session cookie for approval", async () => {
    const response = await approveWorkflow(
      new Request("http://localhost/api/workflows/wf-1/approve", {
        method: "POST",
        body: JSON.stringify({ approved: true, plan_hash: "hash-1" })
      }),
      { params: Promise.resolve({ workflowId: "wf-1" }) }
    );

    expect(response.status).toBe(401);
  });

  it("approves workflow through Agent Service with sanitized session context", async () => {
    vi.stubEnv("AUTH0_SESSION_SECRET", "01234567890123456789012345678901");
    vi.stubEnv("INTERNAL_SERVICE_AUTH_SECRET", "01234567890123456789012345678901");
    vi.stubEnv("AGENT_SERVICE_URL", "http://agent-service.test");
    const fetchMock = vi.fn(async () =>
      Response.json({
        workflow: {
          workflow_id: "wf-1",
          status: "completed",
          auth_context_ref: "raw-auth0-access-token",
          egress_results: [
            {
              obo_token_ref: "obo:approval-secret",
              nested: { keep: "safe-egress", oboTokenRef: "obo:nested-secret" }
            }
          ],
          nested: { access_token: "raw-access-token", keep: "safe" }
        },
        token_exchange: { attempted: true, access_token: "raw-access-token" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const cookie = createAuth0SessionCookieValue(session, 3600);
    const response = await approveWorkflow(
      new Request("http://localhost/api/workflows/wf-1/approve", {
        method: "POST",
        headers: {
          cookie: `${AUTH0_SESSION_COOKIE}=${cookie}`,
          "content-type": "application/json"
        },
        body: JSON.stringify({
          approved: true,
          auth_context_ref: "browser-auth-context",
          plan_hash: "hash-1",
          user_id: "attacker"
        })
      }),
      { params: Promise.resolve({ workflowId: "wf-1" }) }
    );

    expect(response.status).toBe(200);
    const responsePayload = await response.json();
    expect(responsePayload).toMatchObject({
      workflow: {
        workflow_id: "wf-1",
        status: "completed",
        egress_results: [{ nested: { keep: "safe-egress" } }],
        nested: { keep: "safe" }
      }
    });
    expect(JSON.stringify(responsePayload)).not.toContain("auth_context_ref");
    expect(JSON.stringify(responsePayload)).not.toContain("obo:");
    expect(JSON.stringify(responsePayload)).not.toContain("obo_token_ref");
    expect(JSON.stringify(responsePayload)).not.toContain("oboTokenRef");
    expect(JSON.stringify(responsePayload)).not.toContain("raw-auth0-access-token");
    expect(JSON.stringify(responsePayload)).not.toContain("raw-access-token");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://agent-service.test/workflows/wf-1/approve",
      expect.objectContaining({
        body: expect.stringContaining('"plan_hash":"hash-1"')
      })
    );
    const body = String(fetchMock.mock.calls[0]?.[1]?.body);
    expect(body).toContain('"approved":true');
    expect(body).toContain('"plan_hash":"hash-1"');
    expect(body).not.toContain('"approved_by_user_id"');
    expect(body).not.toContain('"session_id"');
    expect(body).not.toContain('"user_id"');
    expect(body).not.toContain("attacker");
    expect(body).not.toContain("auth_context_ref");
    expect(body).not.toContain("browser-auth-context");
    expect(body).not.toContain("raw-auth0-access-token");
    expect(body).not.toContain("access_token");
    expect(body).not.toContain("id_token");
  });

  it("rejects malformed approval payloads before Agent Service", async () => {
    vi.stubEnv("AUTH0_SESSION_SECRET", "01234567890123456789012345678901");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const cookie = createAuth0SessionCookieValue(session, 3600);

    const missingPlanHash = await approveWorkflow(
      new Request("http://localhost/api/workflows/wf-1/approve", {
        method: "POST",
        headers: {
          cookie: `${AUTH0_SESSION_COOKIE}=${cookie}`,
          "content-type": "application/json"
        },
        body: JSON.stringify({ approved: true })
      }),
      { params: Promise.resolve({ workflowId: "wf-1" }) }
    );
    expect(missingPlanHash.status).toBe(400);
    await expect(missingPlanHash.json()).resolves.toEqual({
      error: "plan_hash is required"
    });

    const nonBooleanApproval = await approveWorkflow(
      new Request("http://localhost/api/workflows/wf-1/approve", {
        method: "POST",
        headers: {
          cookie: `${AUTH0_SESSION_COOKIE}=${cookie}`,
          "content-type": "application/json"
        },
        body: JSON.stringify({ approved: "true", plan_hash: "hash-1" })
      }),
      { params: Promise.resolve({ workflowId: "wf-1" }) }
    );
    expect(nonBooleanApproval.status).toBe(400);
    await expect(nonBooleanApproval.json()).resolves.toEqual({
      error: "approved must be a boolean"
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("restores workflow from Agent Service using only the signed Auth0 cookie identity", async () => {
    vi.stubEnv("AUTH0_SESSION_SECRET", "01234567890123456789012345678901");
    vi.stubEnv("INTERNAL_SERVICE_AUTH_SECRET", "01234567890123456789012345678901");
    vi.stubEnv("AGENT_SERVICE_URL", "http://agent-service.test");
    const fetchMock = vi.fn(async () =>
      Response.json({
        workflow: {
          workflow_id: "wf-1",
          status: "awaiting_approval",
          auth_context_ref: "raw-auth0-access-token",
          nested: {
            access_token: "raw-access-token",
            keep: "safe"
          }
        }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const cookie = createAuth0SessionCookieValue(session, 3600);
    const response = await restoreWorkflow(
      new Request("http://localhost/api/workflows/wf-1", {
        method: "GET",
        headers: {
          cookie: `${AUTH0_SESSION_COOKIE}=${cookie}`
        }
      }),
      { params: Promise.resolve({ workflowId: "wf-1" }) }
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      workflow: {
        workflow_id: "wf-1",
        status: "awaiting_approval",
        nested: {
          keep: "safe"
        }
      }
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://agent-service.test/workflows/wf-1",
      expect.objectContaining({
        cache: "no-store",
        method: "GET"
      })
    );
    const forwarded = JSON.stringify(fetchMock.mock.calls[0]);
    expect(forwarded).not.toContain("auth_context_ref");
    expect(forwarded).not.toContain("raw-auth0-access-token");
    expect(forwarded).not.toContain("raw-access-token");
  });
});

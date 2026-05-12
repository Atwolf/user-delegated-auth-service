import { afterEach, describe, expect, it, vi } from "vitest";
import { POST as createThread } from "@/app/api/threads/route";
import { POST as restoreThread } from "@/app/api/threads/[threadId]/route";
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

describe("thread proxy routes", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("requires a signed Auth0 session cookie for thread creation", async () => {
    const response = await createThread(
      new Request("http://localhost/api/threads", { method: "POST" })
    );

    expect(response.status).toBe(401);
  });

  it("creates threads through Agent Service with sanitized session context", async () => {
    vi.stubEnv("AUTH0_SESSION_SECRET", "01234567890123456789012345678901");
    vi.stubEnv("INTERNAL_SERVICE_AUTH_SECRET", "01234567890123456789012345678901");
    vi.stubEnv("AGENT_SERVICE_URL", "http://agent-service.test");
    const fetchMock = vi.fn(async () =>
      Response.json({ messages: [], state: {}, thread_id: "thread-1" })
    );
    vi.stubGlobal("fetch", fetchMock);

    const cookie = createAuth0SessionCookieValue(session, 3600);
    const response = await createThread(
      new Request("http://localhost/api/threads", {
        method: "POST",
        headers: {
          cookie: `${AUTH0_SESSION_COOKIE}=${cookie}`,
          "content-type": "application/json"
        },
        body: JSON.stringify({ title: "Ops" })
      })
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({ threadId: "thread-1" });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://agent-service.test/threads",
      expect.objectContaining({
        body: expect.stringContaining('"user_id":"auth0|user-1"')
      })
    );
    const body = String(fetchMock.mock.calls[0]?.[1]?.body);
    expect(body).toContain('"title":"Ops"');
    expect(body).toContain('"allowed_tools":["inspect_dns_record","inspect_vm"]');
    expect(body).not.toContain("auth_context_ref");
    expect(body).not.toContain("raw-auth0-access-token");
  });

  it("restores threads through Agent Service with sanitized session context", async () => {
    vi.stubEnv("AUTH0_SESSION_SECRET", "01234567890123456789012345678901");
    vi.stubEnv("INTERNAL_SERVICE_AUTH_SECRET", "01234567890123456789012345678901");
    vi.stubEnv("AGENT_SERVICE_URL", "http://agent-service.test");
    const fetchMock = vi.fn(async () =>
      Response.json({ messages: [{ role: "assistant" }], state: { ok: true } })
    );
    vi.stubGlobal("fetch", fetchMock);

    const cookie = createAuth0SessionCookieValue(session, 3600);
    const response = await restoreThread(
      new Request("http://localhost/api/threads/thread-1", {
        method: "POST",
        headers: {
          cookie: `${AUTH0_SESSION_COOKIE}=${cookie}`
        }
      }),
      { params: Promise.resolve({ threadId: "thread-1" }) }
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({
      state: { ok: true },
      threadId: "thread-1"
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://agent-service.test/threads/thread-1",
      expect.objectContaining({
        method: "GET"
      })
    );
  });
});

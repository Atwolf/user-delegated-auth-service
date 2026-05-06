import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Auth0ConfigPanel } from "@/components/auth0-config-panel";
import { WorkflowContextProvider } from "@/components/workflow-context";

const SESSION_PAYLOAD = {
  session: {
    sessionId: "auth0-session-1",
    tokenRef: "auth0:sample",
    scope: "read:apps read:users",
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
  }
};

describe("Auth0 user login panel", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("does not expose raw OIDC or token configuration fields", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ session: null })));

    render(
      <WorkflowContextProvider>
        <Auth0ConfigPanel />
      </WorkflowContextProvider>
    );

    expect(screen.getByRole("link", { name: /log in with auth0/i })).toHaveAttribute(
      "href",
      "/api/auth/login"
    );
    expect(screen.queryByLabelText(/oidc client id/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/client secret/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/token endpoint/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/token keys endpoint/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/user password/i)).not.toBeInTheDocument();
  });

  it("renders the server-side Auth0 user session state", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json(SESSION_PAYLOAD)));

    render(
      <WorkflowContextProvider>
        <Auth0ConfigPanel />
      </WorkflowContextProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/logged in as sample@example.com/i)).toBeInTheDocument();
    });
    expect(screen.getByText("read:apps")).toBeInTheDocument();
    expect(screen.getByText("get_developer_app")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /log out/i })).toHaveAttribute(
      "href",
      "/api/auth/logout"
    );
  });
});

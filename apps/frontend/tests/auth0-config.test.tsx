import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, beforeEach } from "vitest";
import { Auth0ConfigPanel } from "@/components/auth0-config-panel";
import { WorkflowContextProvider } from "@/components/workflow-context";
import {
  AUTH0_STORAGE_KEY,
  DEFAULT_AUTH0_CONFIG,
  savePublicConfig,
  validateAuth0Config
} from "@/lib/auth0-config";

describe("Auth0 config", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("validates required client credentials fields", () => {
    const invalid = validateAuth0Config({
      ...DEFAULT_AUTH0_CONFIG,
      clientId: "",
      clientSecret: ""
    });

    expect(invalid.valid).toBe(false);
    expect(invalid.errors.clientId).toBeTruthy();
    expect(invalid.errors.clientSecret).toBeTruthy();

    const valid = validateAuth0Config({
      ...DEFAULT_AUTH0_CONFIG,
      clientId: "client-id",
      clientSecret: "client-secret"
    });
    expect(valid.valid).toBe(true);
  });

  it("persists public config without the client secret", () => {
    savePublicConfig(window.localStorage, {
      ...DEFAULT_AUTH0_CONFIG,
      clientId: "client-id",
      audience: "https://api.example.test"
    });

    const raw = window.localStorage.getItem(AUTH0_STORAGE_KEY);
    expect(raw).toContain("client-id");
    expect(raw).not.toContain("client-secret");
  });

  it("keeps secret input out of localStorage", () => {
    render(
      <WorkflowContextProvider>
        <Auth0ConfigPanel />
      </WorkflowContextProvider>
    );

    fireEvent.change(screen.getByLabelText("OIDC Client ID"), {
      target: { value: "client-id" }
    });
    fireEvent.change(screen.getByLabelText("OIDC Client Secret"), {
      target: { value: "client-secret" }
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    expect(window.localStorage.getItem(AUTH0_STORAGE_KEY)).toContain("client-id");
    expect(window.localStorage.getItem(AUTH0_STORAGE_KEY)).not.toContain("client-secret");
  });
});

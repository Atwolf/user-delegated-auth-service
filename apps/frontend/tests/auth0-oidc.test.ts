import { describe, expect, it } from "vitest";
import { createAuth0Transaction } from "@/lib/server/auth0-oidc";

describe("Auth0 OIDC transaction", () => {
  it("allows only same-origin return paths", () => {
    expect(createAuth0Transaction("/workflows?tab=active").returnTo).toBe(
      "/workflows?tab=active"
    );
    expect(createAuth0Transaction("https://evil.example").returnTo).toBe("/");
    expect(createAuth0Transaction("//evil.example/path").returnTo).toBe("/");
    expect(createAuth0Transaction("/\\evil.example").returnTo).toBe("/");
  });
});

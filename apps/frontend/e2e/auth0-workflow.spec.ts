import { expect, test } from "@playwright/test";

const hasRealAuth0Env = Boolean(
  process.env.AUTH0_CLIENT_ID &&
    process.env.AUTH0_CLIENT_SECRET &&
    process.env.AUTH0_AUDIENCE
);

test.skip(
  !hasRealAuth0Env,
  "Real Auth0 E2E requires AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET, and AUTH0_AUDIENCE"
);

test("Auth0 config drives plan approval execution", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("OIDC Client ID").fill(process.env.AUTH0_CLIENT_ID ?? "");
  await page.getByLabel("OIDC Client Secret").fill(process.env.AUTH0_CLIENT_SECRET ?? "");
  await page.getByLabel("Audience (optional)").fill(process.env.AUTH0_AUDIENCE ?? "");
  await page.getByRole("button", { name: /save/i }).click();

  await page.getByLabel("Workflow chat input").fill("Check user sample-user and app sample-app");
  await page.getByTitle("Send message").click();

  await expect(page.getByTestId("approval-card")).toBeVisible();
  await expect(page.getByText("get_identity_profile")).toBeVisible();
  await expect(page.getByTestId("approval-card").getByText(/^DOE\./)).toHaveCount(0);

  await page.getByRole("button", { name: /approve workflow/i }).click();
  await expect(page.getByRole("button", { name: /completed/i })).toBeVisible();
});

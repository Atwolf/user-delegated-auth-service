import { expect, test } from "@playwright/test";

test("Auth0 config drives plan approval execution", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("OIDC Client ID").fill("sample-client-id");
  await page.getByLabel("OIDC Client Secret").fill("sample-client-secret");
  await page.getByRole("button", { name: /save/i }).click();

  await page.getByLabel("Workflow chat input").fill("Check user sample-user and app sample-app");
  await page.getByTitle("Send message").click();

  await expect(page.getByTestId("approval-card")).toBeVisible();
  await expect(page.getByText("get_identity_profile")).toBeVisible();
  await expect(page.getByText("DOE.Identity.sample-user").first()).toBeVisible();

  await page.getByRole("button", { name: /approve workflow/i }).click();
  await expect(page.getByRole("button", { name: /completed/i })).toBeVisible();
});

import { expect, test } from "@playwright/test";

const hasRealAuth0Env = Boolean(
  process.env.AUTH0_DOMAIN &&
    process.env.AUTH0_USER_CLIENT_ID &&
    process.env.AUTH0_AUDIENCE &&
    process.env.AUTH0_SESSION_SECRET &&
    process.env.AUTH0_SAMPLE_USER_IDENTITY_DEVELOPER_EMAIL &&
    process.env.AUTH0_SAMPLE_USER_IDENTITY_DEVELOPER_PASSWORD
);

test.skip(
  !hasRealAuth0Env,
  "Real Auth0 E2E requires Auth0 tenant config plus a sample user email and password"
);

test("Auth0 user login drives the AG-UI assistant runtime", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/authorize/);

  await expect(page.getByLabel(/oidc client id/i)).toHaveCount(0);
  await expect(page.getByLabel(/client secret/i)).toHaveCount(0);
  await expect(page.getByLabel(/token endpoint/i)).toHaveCount(0);

  await page
    .getByLabel(/email/i)
    .fill(process.env.AUTH0_SAMPLE_USER_IDENTITY_DEVELOPER_EMAIL ?? "");
  await page
    .getByLabel(/password/i)
    .fill(process.env.AUTH0_SAMPLE_USER_IDENTITY_DEVELOPER_PASSWORD ?? "");
  await page.getByRole("button", { name: /continue|log in|login/i }).click();
  await expect(page.getByText(/logged in as/i)).toBeVisible();

  await page.getByLabel("Assistant message").fill("Check user sample-user and app sample-app");
  const agUiRequest = page.waitForRequest(/\/api\/ag-ui$/);
  await page.getByTitle("Send message").click();
  await agUiRequest;
});

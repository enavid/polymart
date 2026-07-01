/**
 * Access control from the browser: a logged-out visitor must not reach
 * authenticated surfaces or see protected data. These run in the `public`
 * project, which carries no saved session.
 */

import { expect, test } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { CHANNEL } from "../fixtures/seed";

test("logged-out visitor is asked to sign in on the cart page", async ({ page }) => {
  await page.goto("/cart");
  await expect(page.getByText(messages.cart.loginRequired)).toBeVisible();
  // No cart data/table is rendered.
  await expect(page.getByText(messages.cart.total, { exact: true })).toHaveCount(0);
});

test("logged-out visitor sees the not-logged-in state on the account page", async ({ page }) => {
  await page.goto("/account");
  await expect(page.getByText(messages.account.notLoggedIn)).toBeVisible();
});

test("logged-out visitor cannot see protected admin data (channels)", async ({ page }) => {
  await page.goto("/admin/channels");
  // The page loads, but the API rejects the unauthenticated read, so the seeded
  // channel's data never renders -- no protected data is leaked to the browser.
  await expect(page.getByRole("cell", { name: CHANNEL, exact: true })).toHaveCount(0);
});

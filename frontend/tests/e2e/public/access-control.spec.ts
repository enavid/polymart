/**
 * Access control from the browser: a logged-out visitor must not reach
 * authenticated surfaces or see protected data. These run in the `public`
 * project, which carries no saved session.
 */

import { expect, test } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { CHANNEL } from "../fixtures/seed";

test("logged-out visitor can use the cart without a sign-in gate (guest checkout)", async ({
  page,
}) => {
  await page.goto("/cart");
  // The cart is a guest-accessible surface now: a fresh visitor sees their own (empty)
  // cart rather than a "please sign in" gate. Building + checking it out as a guest is
  // covered end to end by the guest-checkout spec.
  await expect(page.getByText(messages.cart.empty)).toBeVisible();
});

test("logged-out visitor sees the not-logged-in state on the account page", async ({ page }) => {
  await page.goto("/account");
  await expect(page.getByText(messages.account.notLoggedIn)).toBeVisible();
});

test("logged-out visitor cannot see protected admin data (channels)", async ({ page }) => {
  await page.goto("/manage/channels");
  // The page loads, but the API rejects the unauthenticated read, so the seeded
  // channel's data never renders -- no protected data is leaked to the browser.
  await expect(page.getByRole("cell", { name: CHANNEL, exact: true })).toHaveCount(0);
});

/**
 * The account page for the authenticated shopper (reusing the saved session).
 * It reads /auth/me from the real backend and renders the profile.
 *
 * This does not log out -- the shopper session is shared across the shopper
 * project's specs, so tearing it down here would break the others.
 */

import { expect, test } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { SHOPPER } from "../fixtures/seed";

const account = messages.account;

test("account page shows the signed-in shopper's profile", async ({ page }) => {
  await page.goto("/account");

  await expect(page.getByRole("heading", { name: account.title })).toBeVisible();
  await expect(page.getByText(SHOPPER.canonicalPhone)).toBeVisible();
  await expect(page.getByText(SHOPPER.fullName, { exact: true })).toBeVisible();
  // The shopper is not staff.
  await expect(page.getByText(account.staffLabel)).toBeVisible();
  await expect(page.getByText(account.no, { exact: true })).toBeVisible();
});

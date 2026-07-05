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

  // Scope profile assertions to <main>: the header account menu also shows the shopper's
  // name, so an unscoped getByText would match two elements (strict-mode violation).
  const main = page.getByRole("main");
  await expect(page.getByRole("heading", { name: account.title })).toBeVisible();
  await expect(main.getByText(SHOPPER.canonicalPhone)).toBeVisible();
  await expect(main.getByText(SHOPPER.fullName, { exact: true })).toBeVisible();
  // The shopper is not staff.
  await expect(main.getByText(account.staffLabel)).toBeVisible();
  await expect(main.getByText(account.no, { exact: true })).toBeVisible();
});

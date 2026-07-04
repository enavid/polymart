/**
 * Guest cart merge on login, end to end against the real backend (slice C).
 *
 * A visitor builds a cart as a guest (kept by the HttpOnly guest_session cookie the
 * backend mints on the first write), then signs in. The backend folds the guest cart
 * into the user's cart and expires the guest cookie, so after login the shopper sees
 * the items they added while anonymous.
 *
 *   browse -> add as guest -> cart shows the line (no login) -> log in ->
 *   the same line is now in the signed-in user's cart.
 *
 * Runs in the `public` project (each test gets a fresh context, hence a fresh guest
 * token and no saved session). It signs in as the STAFF user, whose cart no other spec
 * touches, and empties that cart at the end so the shared seeded state stays pristine
 * regardless of run order.
 */

import { expect, test, type Page } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { PRODUCTS, STAFF } from "../fixtures/seed";

const cart = messages.cart;
const store = messages.storefront;
const auth = messages.auth;
const common = messages.common;
const dr250 = PRODUCTS.darkRoast.variants[0]; // 150,000

async function addFromPdp(page: Page, productCode: string, sku: string): Promise<void> {
  await page.goto(`/products/${productCode}`);
  const qty = page.locator(`#variant_qty_${sku}`);
  await expect(qty).toBeVisible();
  await qty.fill("1");
  await qty.locator("xpath=..").getByRole("button", { name: store.addToCart }).click();
  await expect(page.getByText(store.added)).toBeVisible();
}

async function logIn(page: Page): Promise<void> {
  await page.goto("/login?next=/account");
  await page.getByLabel(common.phoneNumber).fill(STAFF.phone);
  await page.getByLabel(common.password).fill(STAFF.password);
  await page.getByRole("button", { name: auth.loginCta }).click();
  // Login returns to the requested page (/account) on success.
  await expect(page).toHaveURL(/\/account/);
}

test("guest cart merges into the user's cart on login", async ({ page }) => {
  const line = page.getByRole("row", { name: new RegExp(dr250.sku) });

  // 1) As a guest (no session), add a line. The cart shows it with no login gate.
  await addFromPdp(page, PRODUCTS.darkRoast.code, dr250.sku);
  await page.goto("/cart");
  await expect(line).toBeVisible();

  // 2) Sign in. The backend merges the guest cart into the user's on login.
  await logIn(page);

  // 3) The item added anonymously is now in the signed-in user's cart.
  await page.goto("/cart");
  await expect(line).toBeVisible();
  await expect(page.getByText(cart.empty)).toBeHidden();

  // Cleanup: empty the user's cart so the shared seeded staff account stays pristine.
  await line.getByRole("button", { name: cart.remove }).click();
  await expect(page.getByText(cart.empty)).toBeVisible();
});

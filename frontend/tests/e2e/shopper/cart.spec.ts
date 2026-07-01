/**
 * The authenticated shopper's cart journey, end to end against the real backend.
 * A deliberately rigorous single flow (the cart is one shared resource for the
 * seeded shopper, cleared before every run, so parallel tests would race):
 *
 *   empty -> add -> add again (accumulates) -> add a second line ->
 *   multi-line total -> update quantity -> remove one line -> remove the last.
 *
 * Every money value is asserted by reproducing the UI's own formatting, so we
 * check the *displayed server value* and never a client-side recomputation.
 */

import { expect, test } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { PRODUCTS } from "../fixtures/seed";

const cart = messages.cart;
const store = messages.storefront;
const hb250 = PRODUCTS.houseBlend.variants[0]; // 120,000
const hb500 = PRODUCTS.houseBlend.variants[1]; // 200,000

function money(amount: number): string {
  return new Intl.NumberFormat("fa-IR", { style: "currency", currency: "IRR" }).format(amount);
}

async function addFromPdp(page: import("@playwright/test").Page, sku: string): Promise<void> {
  await page.goto(`/products/${PRODUCTS.houseBlend.code}`);
  const qty = page.locator(`#variant_qty_${sku}`);
  await expect(qty).toBeVisible();
  await qty.fill("1");
  await qty.locator("xpath=..").getByRole("button", { name: store.addToCart }).click();
  await expect(page.getByText(store.added)).toBeVisible();
}

test("shopper cart: add, accumulate, multi-line total, update, and remove", async ({ page }) => {
  // 1) Seeded cart starts empty.
  await page.goto("/cart");
  await expect(page.getByText(cart.empty)).toBeVisible();

  // 2) Add HB-250 twice (x1 each): the same SKU accumulates rather than duplicating.
  await addFromPdp(page, hb250.sku);
  await addFromPdp(page, hb250.sku);
  // 3) Add a second line, HB-500 x1.
  await addFromPdp(page, hb500.sku);

  // 4) The cart shows HB-250 at quantity 2 (accumulated) and a server-computed
  //    multi-line total: 2*120,000 + 1*200,000 = 440,000.
  await page.goto("/cart");
  await expect(page.locator(`#cart_qty_${hb250.sku}`)).toHaveValue("2");
  await expect(page.getByText(hb500.sku, { exact: true })).toBeVisible();
  await expect(page.getByText(money(440000)).first()).toBeVisible();

  // 5) Update HB-250 to 3 -> 3*120,000 + 200,000 = 560,000.
  const q = page.locator(`#cart_qty_${hb250.sku}`);
  await q.fill("3");
  await q.locator("xpath=..").getByRole("button", { name: cart.update }).click();
  await expect(page.getByText(money(560000)).first()).toBeVisible();

  // 6) Remove HB-500 -> only HB-250 x3 remains: 360,000.
  await page
    .getByRole("row", { name: new RegExp(hb500.sku) })
    .getByRole("button", { name: cart.remove })
    .click();
  await expect(page.getByText(hb500.sku, { exact: true })).toHaveCount(0);
  await expect(page.getByText(money(360000)).first()).toBeVisible();

  // 7) Remove the last line -> empty again.
  await page.getByRole("button", { name: cart.remove }).click();
  await expect(page.getByText(cart.empty)).toBeVisible();
});

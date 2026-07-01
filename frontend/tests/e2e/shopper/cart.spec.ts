/**
 * The authenticated shopper's cart journey, end to end against the real backend:
 * start empty, add a variant from the PDP, see the *dynamically priced* line and
 * total, update the quantity, then remove the line and land back on empty.
 *
 * The cart is a single shared resource for the seeded shopper (the seed clears it
 * before every run), so this is one ordered flow rather than parallel tests that
 * would race on the same cart.
 */

import { expect, test } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { PRODUCTS } from "../fixtures/seed";

const cart = messages.cart;
const store = messages.storefront;
const variant = PRODUCTS.houseBlend.variants[0]; // HB-250 @ 120,000

/** Reproduce the UI's money formatting so we assert the *displayed* server value. */
function money(amount: number): string {
  return new Intl.NumberFormat("fa-IR", { style: "currency", currency: "IRR" }).format(amount);
}

test("shopper adds a variant, sees dynamic pricing, updates quantity, then removes it", async ({
  page,
}) => {
  // 1) The seeded cart starts empty.
  await page.goto("/cart");
  await expect(page.getByRole("heading", { name: cart.title })).toBeVisible();
  await expect(page.getByText(cart.empty)).toBeVisible();

  // 2) Add HB-250 x2 from the product detail page.
  await page.goto(`/products/${PRODUCTS.houseBlend.code}`);
  const qty = page.locator(`#variant_qty_${variant.sku}`);
  await expect(qty).toBeVisible();
  await qty.fill("2");
  await qty.locator("xpath=..").getByRole("button", { name: store.addToCart }).click();
  await expect(page.getByText(store.added)).toBeVisible();

  // 3) The cart shows the line, its unit price, and a server-computed total
  //    (2 x 120,000 = 240,000). The UI renders the backend's amount, never a
  //    client-side recomputation.
  await page.goto("/cart");
  await expect(page.getByText(variant.sku, { exact: true })).toBeVisible();
  await expect(page.getByText(money(120000)).first()).toBeVisible();
  await expect(page.getByText(money(240000)).first()).toBeVisible();

  // 4) Update the quantity to 3 -> line total and cart total both become 360,000.
  const cartQty = page.locator(`#cart_qty_${variant.sku}`);
  await cartQty.fill("3");
  await cartQty.locator("xpath=..").getByRole("button", { name: cart.update }).click();
  await expect(page.getByText(money(360000)).first()).toBeVisible();
  await expect(page.getByText(money(240000))).toHaveCount(0);

  // 5) Remove the line -> the cart is empty again.
  await page.getByRole("button", { name: cart.remove }).click();
  await expect(page.getByText(cart.empty)).toBeVisible();
});

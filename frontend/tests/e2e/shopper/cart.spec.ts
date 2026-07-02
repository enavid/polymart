/**
 * The authenticated shopper's cart + checkout journey, end to end against the real
 * backend. The seeded shopper is one shared resource (a single cart, one stock pool,
 * one order history, all reset before every run), so these run **serially in one
 * worker** -- parallel tests would race on that shared state.
 *
 *   cart:     empty -> add -> add again (accumulates) -> second line ->
 *             multi-line total -> update quantity -> remove one -> remove last.
 *   checkout: add -> place order -> order confirmation (captured total + status) ->
 *             appears in history -> cancel (restocks) -> IDOR (staff cannot see it).
 *   oversell: a priced-but-zero-stock line cannot be checked out (409 surfaced).
 *
 * Every money value is asserted by reproducing the UI's own formatting, so we check
 * the *displayed server value* and never a client-side recomputation.
 */

import { expect, test } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { PRODUCTS, STAFF_STATE } from "../fixtures/seed";

const cart = messages.cart;
const store = messages.storefront;
const orders = messages.orders;
const hb250 = PRODUCTS.houseBlend.variants[0]; // 120,000
const hb500 = PRODUCTS.houseBlend.variants[1]; // 200,000
const dr250 = PRODUCTS.darkRoast.variants[0]; // 150,000, stock 5
const lr250 = PRODUCTS.lightRoast.variants[0]; // 100,000, stock 0 (priced but unstocked)

function money(amount: number): string {
  return new Intl.NumberFormat("fa-IR", { style: "currency", currency: "IRR" }).format(amount);
}

async function addFromPdp(
  page: import("@playwright/test").Page,
  productCode: string,
  sku: string,
): Promise<void> {
  await page.goto(`/products/${productCode}`);
  const qty = page.locator(`#variant_qty_${sku}`);
  await expect(qty).toBeVisible();
  await qty.fill("1");
  await qty.locator("xpath=..").getByRole("button", { name: store.addToCart }).click();
  await expect(page.getByText(store.added)).toBeVisible();
}

test.describe.serial("shopper cart & checkout", () => {
  test("cart: add, accumulate, multi-line total, update, and remove", async ({ page }) => {
    // 1) Seeded cart starts empty.
    await page.goto("/cart");
    await expect(page.getByText(cart.empty)).toBeVisible();

    // 2) Add HB-250 twice (x1 each): the same SKU accumulates rather than duplicating.
    await addFromPdp(page, PRODUCTS.houseBlend.code, hb250.sku);
    await addFromPdp(page, PRODUCTS.houseBlend.code, hb250.sku);
    // 3) Add a second line, HB-500 x1.
    await addFromPdp(page, PRODUCTS.houseBlend.code, hb500.sku);

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

  test("checkout: place an order, see it, and cancel it (restocking)", async ({ page, browser }) => {
    // Add one DR-250 (150,000, stock 5) and check out.
    await addFromPdp(page, PRODUCTS.darkRoast.code, dr250.sku);
    await page.goto("/cart");
    await expect(page.getByText(money(150000)).first()).toBeVisible();
    await page.getByRole("button", { name: cart.checkout }).click();

    // Landed on the order confirmation: captured total + pending status.
    await expect(page).toHaveURL(/\/orders\/ORD-/);
    const orderNumber = page.url().split("/orders/")[1].replace(/\/$/, "");
    await expect(page.getByText(orderNumber).first()).toBeVisible();
    await expect(page.getByText(orders.statusPending).first()).toBeVisible();
    await expect(page.getByText(money(150000)).first()).toBeVisible();

    // The cart is now empty (consumed by checkout).
    await page.goto("/cart");
    await expect(page.getByText(cart.empty)).toBeVisible();

    // The order appears in history.
    await page.goto("/orders");
    await expect(page.getByText(orderNumber).first()).toBeVisible();

    // IDOR: the staff user (a different account) must not be able to see it.
    const staffContext = await browser.newContext({ storageState: STAFF_STATE });
    const staffPage = await staffContext.newPage();
    await staffPage.goto(`/orders/${orderNumber}`);
    await expect(staffPage.getByText(orders.notFound)).toBeVisible();
    await staffContext.close();

    // Cancel the order via the inline confirmation; stock is returned.
    await page.goto(`/orders/${orderNumber}`);
    await page.getByRole("button", { name: orders.cancel }).click();
    await expect(page.getByText(orders.cancelConfirm)).toBeVisible();
    await page.getByRole("button", { name: orders.cancel }).click();
    await expect(page.getByText(orders.cancelledNote)).toBeVisible();
    await expect(page.getByText(orders.statusCancelled).first()).toBeVisible();
  });

  test("checkout: a priced but out-of-stock line cannot be ordered", async ({ page }) => {
    // LR-250 is priced (100,000) but seeded with zero stock: it can be added to the
    // cart, but checkout must refuse the oversell rather than place an order.
    await addFromPdp(page, PRODUCTS.lightRoast.code, lr250.sku);
    await page.goto("/cart");
    await page.getByRole("button", { name: cart.checkout }).click();

    // Stays on the cart with a conflict message; no navigation to an order.
    await expect(page.getByText(cart.checkoutError)).toBeVisible();
    await expect(page).toHaveURL(/\/cart/);

    // Clean up so the shared cart is empty for any later run.
    await page
      .getByRole("row", { name: new RegExp(lr250.sku) })
      .getByRole("button", { name: cart.remove })
      .click();
    await expect(page.getByText(cart.empty)).toBeVisible();
  });
});

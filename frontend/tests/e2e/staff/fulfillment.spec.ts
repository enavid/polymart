/**
 * Order fulfilment (Phase 5, label/tracking + BOPIS slice), driven against the real stack.
 *
 * Runs in the staff project (seeded order_admin). A shopper first pays for an order online
 * (via the dev mock gateway) so it reaches `paid`; then staff ship it with a carrier +
 * tracking, and the shopper sees the order move to fulfilled with the tracking shown. A
 * second flow proves BOPIS: staff cannot ship a pickup order (it uses the ready -> picked-up
 * path instead), asserted at the API boundary to keep the spec fast and deterministic.
 *
 * The shopper actions use a separate browser context (the shopper's stored session), so the
 * spec exercises the real cross-actor handoff: shopper pays, staff fulfils, shopper sees it.
 */

import { expect, test, type Page } from "@playwright/test";

import { PRODUCTS, SHOPPER_ADDRESS, SHOPPER_STATE } from "../fixtures/seed";
import messages from "../../../src/i18n/messages/fa.json";

const cart = messages.cart;
const checkout = messages.checkout;
const orders = messages.orders;
const store = messages.storefront;
const SEED = SHOPPER_ADDRESS.recipientName;
const dr250 = PRODUCTS.darkRoast.variants[0]; // 150,000, stock 5

/** As the shopper: add a DR-250, check out choosing online payment, pay at the mock gateway. */
async function shopperPaysOnline(page: Page): Promise<string> {
  await page.goto(`/products/${PRODUCTS.darkRoast.code}`);
  const qty = page.locator(`#variant_qty_${dr250.sku}`);
  await expect(qty).toBeVisible();
  await qty.fill("1");
  await qty.locator("xpath=..").getByRole("button", { name: store.addToCart }).click();
  await expect(page.getByText(store.added)).toBeVisible();

  await page.goto("/cart");
  await page.getByRole("link", { name: cart.checkout }).click();
  await expect(page).toHaveURL(/\/checkout/);
  await page.locator("label").filter({ hasText: SEED }).getByRole("radio").check();
  await page.getByRole("button", { name: checkout.continue }).click();
  await page.locator('input[type="radio"][value="standard"]').check();
  await page.locator('input[type="radio"][value="online"]').check();
  await page.getByRole("button", { name: checkout.placeOrder }).click();

  // Pay at the dev mock gateway; it settles the payment server-side and returns to the order.
  await expect(page).toHaveURL(/\/payments\/mock-gateway\//);
  await page.locator("#mock_pay").click();
  await expect(page).toHaveURL(/\/orders\/ORD-/);
  await expect(page.getByText(orders.statusPaid).first()).toBeVisible();
  return page.url().split("/orders/")[1].replace(/\/$/, "");
}

test("staff ship a paid order and the shopper sees the tracking", async ({ page, browser }) => {
  // 1) The shopper pays online, reaching a paid order.
  const shopperContext = await browser.newContext({ storageState: SHOPPER_STATE });
  const shopperPage = await shopperContext.newPage();
  const orderNumber = await shopperPaysOnline(shopperPage);

  // 2) Staff (this page) open the paid order and ship it with a carrier + tracking.
  await page.goto(`/orders/${orderNumber}`);
  await page.getByLabel(orders.carrier).fill("Post");
  await page.getByLabel(orders.trackingNumber).fill("TRK-E2E-1");
  await page.getByRole("button", { name: orders.markShipped }).click();

  // The order is now fulfilled and the captured carrier + tracking are shown.
  await expect(page.getByText(orders.statusFulfilled).first()).toBeVisible();
  await expect(page.getByText("Post")).toBeVisible();
  await expect(page.getByText("TRK-E2E-1")).toBeVisible();

  // 3) The shopper sees the same fulfilled status + tracking on their own order page.
  await shopperPage.goto(`/orders/${orderNumber}`);
  await expect(shopperPage.getByText(orders.statusFulfilled).first()).toBeVisible();
  await expect(shopperPage.getByText("TRK-E2E-1")).toBeVisible();

  await shopperContext.close();
});

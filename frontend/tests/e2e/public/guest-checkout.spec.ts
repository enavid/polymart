/**
 * The guest (unauthenticated) checkout journey, end to end against the real backend.
 *
 * A visitor with no account builds a cart, checks out with a one-off inline shipping
 * address, and reaches their order -- all identified only by the HttpOnly guest session
 * cookie the backend mints on the first cart write. Runs in the `public` project (no
 * saved auth state), so the browser starts with no session at all.
 *
 *   browse -> add to cart -> cart shows the line (no login gate) -> checkout ->
 *   fill the inline shipping form -> review -> place -> order confirmation
 *   (captured total + pending status + captured recipient) -> cart emptied ->
 *   appears in the guest's own history -> IDOR (a different guest cannot see it) ->
 *   cancel (restocks, keeping the shared stock pool pristine).
 *
 * Each Playwright test gets a fresh context, hence a fresh guest token, so the guest
 * cart starts empty deterministically without any per-run seed reset. Money is asserted
 * by reproducing the UI's own formatting -- the displayed server value, never a
 * client-side recomputation.
 */

import { expect, test, type Page } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { ADDRESS, PRODUCTS } from "../fixtures/seed";

const cart = messages.cart;
const store = messages.storefront;
const orders = messages.orders;
const checkout = messages.checkout;
const addresses = messages.addresses;
const dr250 = PRODUCTS.darkRoast.variants[0]; // 150,000, stock 5

function money(amount: number): string {
  return new Intl.NumberFormat("fa-IR", { style: "currency", currency: "IRR" }).format(amount);
}

async function addFromPdp(page: Page, productCode: string, sku: string): Promise<void> {
  await page.goto(`/products/${productCode}`);
  const qty = page.locator(`#variant_qty_${sku}`);
  await expect(qty).toBeVisible();
  await qty.fill("1");
  await qty.locator("xpath=..").getByRole("button", { name: store.addToCart }).click();
  await expect(page.getByText(store.added)).toBeVisible();
}

async function fillInlineShipping(page: Page): Promise<void> {
  await page.getByLabel(addresses.recipientName).fill(ADDRESS.recipientName);
  await page.getByLabel(addresses.phoneNumber).fill(ADDRESS.phoneNumber);
  await page.getByLabel(addresses.province).fill(ADDRESS.province);
  await page.getByLabel(addresses.city).fill(ADDRESS.city);
  await page.getByLabel(addresses.postalCode).fill(ADDRESS.postalCode);
  await page.getByLabel(addresses.line1).fill(ADDRESS.line1);
  await page.getByRole("button", { name: addresses.save }).click();
}

test("guest: build a cart, check out inline, see the order, then cancel it", async ({
  page,
  browser,
}) => {
  // 1) A brand-new guest: no session, and the cart starts empty (fresh token).
  await page.goto("/cart");
  await expect(page.getByText(cart.empty)).toBeVisible();

  // 2) Add one DR-250 (150,000). The first cart write mints the guest cookie.
  await addFromPdp(page, PRODUCTS.darkRoast.code, dr250.sku);

  // 3) The cart is shown directly -- no "please sign in" gate for a guest.
  await page.goto("/cart");
  await expect(page.getByText(dr250.sku, { exact: true })).toBeVisible();
  await expect(page.getByText(money(150000)).first()).toBeVisible();

  // 4) Checkout: the guest fills a one-off inline shipping form (no address book).
  await page.getByRole("link", { name: cart.checkout }).click();
  await expect(page).toHaveURL(/\/checkout/);
  await expect(page.getByText(checkout.guestAddressHint)).toBeVisible();
  await fillInlineShipping(page);

  // 5) Review, then place the order.
  await page.getByRole("button", { name: checkout.placeOrder }).click();

  // 6) Order confirmation: captured total, pending status, and the captured recipient.
  await expect(page).toHaveURL(/\/orders\/ORD-/);
  const orderNumber = page.url().split("/orders/")[1].replace(/\/$/, "");
  await expect(page.getByText(orders.statusPending).first()).toBeVisible();
  await expect(page.getByText(money(150000)).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: orders.shippingAddress })).toBeVisible();
  await expect(page.getByText(ADDRESS.recipientName)).toBeVisible();

  // 7) The cart is now empty (consumed by checkout).
  await page.goto("/cart");
  await expect(page.getByText(cart.empty)).toBeVisible();

  // 8) The order appears in the guest's own history (scoped by their cookie).
  await page.goto("/orders");
  await expect(page.getByText(orderNumber).first()).toBeVisible();

  // 9) IDOR: a different guest (fresh context, no cookie) must not see the order.
  const otherContext = await browser.newContext();
  const otherPage = await otherContext.newPage();
  await otherPage.goto(`/orders/${orderNumber}`);
  await expect(otherPage.getByText(orders.notFound)).toBeVisible();
  await otherContext.close();

  // 10) Cancel via the inline confirmation; stock is returned so the shared pool stays
  //     pristine for other specs.
  await page.goto(`/orders/${orderNumber}`);
  await page.getByRole("button", { name: orders.cancel }).click();
  await expect(page.getByText(orders.cancelConfirm)).toBeVisible();
  await page.getByRole("button", { name: orders.cancel }).click();
  await expect(page.getByText(orders.cancelledNote)).toBeVisible();
  await expect(page.getByText(orders.statusCancelled).first()).toBeVisible();
});

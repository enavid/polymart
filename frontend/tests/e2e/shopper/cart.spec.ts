/**
 * The authenticated shopper's cart + checkout journey, end to end against the real
 * backend. The seeded shopper is one shared resource (a single cart, one stock pool,
 * one order history, all reset before every run), so these run **serially in one
 * worker** -- parallel tests would race on that shared state.
 *
 *   cart:     empty -> add -> add again (accumulates) -> second line ->
 *             multi-line total -> update quantity -> remove one -> remove last.
 *   checkout: add -> choose the seeded address -> place order -> order confirmation
 *             (captured total + status + captured shipping address) -> appears in
 *             history -> cancel (restocks) -> IDOR (staff cannot see it).
 *   oversell: a priced-but-zero-stock line cannot be checked out (409 surfaced on the
 *             checkout review step).
 *
 * Every money value is asserted by reproducing the UI's own formatting, so we check
 * the *displayed server value* and never a client-side recomputation.
 */

import { expect, test, type Page } from "@playwright/test";

import { formatCurrency } from "../../../src/lib/format";
import messages from "../../../src/i18n/messages/fa.json";
import { PRODUCTS, SHOPPER_ADDRESS, STAFF_STATE } from "../fixtures/seed";

const cart = messages.cart;
const store = messages.storefront;
const orders = messages.orders;
const checkout = messages.checkout;
const payment = messages.payment;
const SEED = SHOPPER_ADDRESS.recipientName;
const hb250 = PRODUCTS.houseBlend.variants[0]; // 120,000
const hb500 = PRODUCTS.houseBlend.variants[1]; // 200,000
const dr250 = PRODUCTS.darkRoast.variants[0]; // 150,000, stock 5
const lr250 = PRODUCTS.lightRoast.variants[0]; // 100,000, stock 0 (priced but unstocked)

function money(amount: number): string {
  // Delegate to the app's own formatter (its single source of truth) so the E2E
  // assertions render money exactly as the UI does -- IRR presented in Toman.
  return formatCurrency(amount, "IRR");
}

async function addFromPdp(page: Page, productCode: string, sku: string): Promise<void> {
  await page.goto(`/products/${productCode}`);
  const qty = page.locator(`#variant_qty_${sku}`);
  await expect(qty).toBeVisible();
  await qty.fill("1");
  await qty.locator("xpath=..").getByRole("button", { name: store.addToCart }).click();
  await expect(page.getByText(store.added)).toBeVisible();
}

/**
 * From the cart, run the multi-step checkout: proceed to the checkout page, select the
 * seeded "home" address explicitly (stable -- the address-book spec never deletes it),
 * continue to review, and place the order.
 */
async function checkoutWithSeededAddress(page: Page): Promise<void> {
  await page.goto("/cart");
  await page.getByRole("link", { name: cart.checkout }).click();
  await expect(page).toHaveURL(/\/checkout/);
  await page.locator("label").filter({ hasText: SEED }).getByRole("radio").check();
  await page.getByRole("button", { name: checkout.continue }).click();
  // The review step offers payment methods: COD is the default (selected), and online and
  // card-to-card are available too. Located by the radio's value (the localized labels
  // contain parentheses, unsafe in a name regex).
  await expect(page.locator('input[type="radio"][value="cod"]')).toBeChecked();
  await expect(page.locator('input[type="radio"][value="card_to_card"]')).toBeEnabled();
  await page.getByRole("button", { name: checkout.placeOrder }).click();
}

/** Checkout choosing the online method: select the seeded address, continue, pick online,
 * and place -- which hands the browser off to the gateway. */
async function checkoutSelectingOnline(page: Page): Promise<void> {
  await page.goto("/cart");
  await page.getByRole("link", { name: cart.checkout }).click();
  await expect(page).toHaveURL(/\/checkout/);
  await page.locator("label").filter({ hasText: SEED }).getByRole("radio").check();
  await page.getByRole("button", { name: checkout.continue }).click();
  await page.locator('input[type="radio"][value="online"]').check();
  await page.getByRole("button", { name: checkout.placeOrder }).click();
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

  test("checkout: select an address, place an order, see it, and cancel it (restocking)", async ({
    page,
    browser,
  }) => {
    // Add one DR-250 (150,000, stock 5) and run the multi-step checkout.
    await addFromPdp(page, PRODUCTS.darkRoast.code, dr250.sku);
    await checkoutWithSeededAddress(page);

    // Landed on the order confirmation: captured total, pending status, and the
    // captured shipping address (a snapshot of the seeded home address).
    await expect(page).toHaveURL(/\/orders\/ORD-/);
    const orderNumber = page.url().split("/orders/")[1].replace(/\/$/, "");
    await expect(page.getByText(orderNumber).first()).toBeVisible();
    await expect(page.getByText(orders.statusPending).first()).toBeVisible();
    await expect(page.getByText(money(150000)).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: orders.shippingAddress })).toBeVisible();
    await expect(page.getByText(SEED)).toBeVisible();

    // The payment initiated at checkout is shown: cash on delivery, awaiting collection.
    await expect(page.getByRole("heading", { name: payment.sectionTitle })).toBeVisible();
    await expect(page.getByText(payment.methodCod)).toBeVisible();

    // The order already has an active payment (the COD one from checkout), so a second
    // initiation is refused by the double-payment guard (409) -- verified with the shopper's
    // authenticated cookies riding along on page.request.
    const secondPayment = await page.request.post("/api/v1/payments/", {
      data: { order_number: orderNumber, method: "card_to_card" },
    });
    expect(secondPayment.status()).toBe(409);

    // The cart is now empty (consumed by checkout).
    await page.goto("/cart");
    await expect(page.getByText(cart.empty)).toBeVisible();

    // The order appears in history.
    await page.goto("/orders");
    await expect(page.getByText(orderNumber).first()).toBeVisible();

    // IDOR: the staff user (a different account) must not be able to see the order, nor
    // read its payment (the payment read is owner-scoped, so it 404s for another account).
    const staffContext = await browser.newContext({ storageState: STAFF_STATE });
    const staffPage = await staffContext.newPage();
    await staffPage.goto(`/orders/${orderNumber}`);
    await expect(staffPage.getByText(orders.notFound)).toBeVisible();
    const stolen = await staffPage.request.get(`/api/v1/payments/for-order/${orderNumber}/`);
    expect(stolen.status()).toBe(404);
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
    // cart and carried through the checkout steps, but placing the order must refuse
    // the oversell (409) rather than create it.
    await addFromPdp(page, PRODUCTS.lightRoast.code, lr250.sku);
    await checkoutWithSeededAddress(page);

    // Stays on the checkout review with a conflict message; no navigation to an order.
    await expect(page.getByText(checkout.placeError)).toBeVisible();
    await expect(page).toHaveURL(/\/checkout/);

    // Clean up so the shared cart is empty for any later run.
    await page.goto("/cart");
    await page
      .getByRole("row", { name: new RegExp(lr250.sku) })
      .getByRole("button", { name: cart.remove })
      .click();
    await expect(page.getByText(cart.empty)).toBeVisible();
  });

  test("checkout: pay online at the gateway, capturing the order", async ({ page }) => {
    // Add one DR-250, check out choosing the online method -> the browser is handed off to
    // the (dev mock) payment gateway.
    await addFromPdp(page, PRODUCTS.darkRoast.code, dr250.sku);
    await checkoutSelectingOnline(page);

    // On the mock gateway page: pay. It calls the backend callback, which captures the
    // payment (server-verified) and redirects back to the now-paid order.
    await expect(page).toHaveURL(/\/payments\/mock-gateway\//);
    await page.locator("#mock_pay").click();

    await expect(page).toHaveURL(/\/orders\/ORD-/);
    await expect(page.getByText(orders.statusPaid).first()).toBeVisible();
    // The payment block shows the online method (captured drives the order to paid).
    await expect(page.getByRole("heading", { name: payment.sectionTitle })).toBeVisible();
    await expect(page.getByText(payment.methodOnline)).toBeVisible();
  });

  test("checkout: cancelling at the gateway fails the payment, order stays pending", async ({
    page,
  }) => {
    await addFromPdp(page, PRODUCTS.darkRoast.code, dr250.sku);
    await checkoutSelectingOnline(page);

    // Cancel at the gateway: the callback fails the payment and the order stays pending
    // (never trusts the redirect -- a cancel is never "paid").
    await expect(page).toHaveURL(/\/payments\/mock-gateway\//);
    await page.locator("#mock_cancel").click();

    await expect(page).toHaveURL(/\/orders\/ORD-/);
    await expect(page.getByText(orders.statusPending).first()).toBeVisible();
    await expect(page.getByText(payment.statusFailed)).toBeVisible();

    // A pending order is cancellable; cancel to restock so the shared pool stays pristine.
    await page.getByRole("button", { name: orders.cancel }).click();
    await page.getByRole("button", { name: orders.cancel }).click();
    await expect(page.getByText(orders.cancelledNote)).toBeVisible();
  });
});

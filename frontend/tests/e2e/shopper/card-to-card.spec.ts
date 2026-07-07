/**
 * Card-to-card payment, end to end against the real backend.
 *
 * The full manual-transfer money flow: the shopper checks out with card-to-card, sees the
 * merchant's server-owned destination card, reports their transfer reference, and a staff
 * member (the only role allowed) confirms it -- which captures the payment and marks the
 * order paid. Covers the authorization boundary (a shopper cannot confirm their own payment)
 * and asserts the destination card / status come from the server, never recomputed client-side.
 *
 * Runs serially in one worker against the shared seeded shopper (cart reset before each run).
 */

import { expect, test, type Page } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { PRODUCTS, SHOPPER_ADDRESS, STAFF_STATE } from "../fixtures/seed";

const cart = messages.cart;
const store = messages.storefront;
const orders = messages.orders;
const checkout = messages.checkout;
const payment = messages.payment;
const SEED = SHOPPER_ADDRESS.recipientName;
const dr250 = PRODUCTS.darkRoast.variants[0];

// The deterministic destination card configured for the ir-main channel in dev/test settings.
const DESTINATION_CARD = "6037-9911-1234-5678";
const TRANSFER = "TRK-556677";

async function addFromPdp(page: Page, productCode: string, sku: string): Promise<void> {
  await page.goto(`/products/${productCode}`);
  const qty = page.locator(`#variant_qty_${sku}`);
  await expect(qty).toBeVisible();
  await qty.fill("1");
  await qty.locator("xpath=..").getByRole("button", { name: store.addToCart }).click();
  await expect(page.getByText(store.added)).toBeVisible();
}

async function checkoutToReview(page: Page): Promise<void> {
  await page.goto("/cart");
  await page.getByRole("link", { name: cart.checkout }).click();
  await expect(page).toHaveURL(/\/checkout/);
  await page.locator("label").filter({ hasText: SEED }).getByRole("radio").check();
  await page.getByRole("button", { name: checkout.continue }).click();
}

test.describe.serial("card-to-card payment", () => {
  test("buyer reports a transfer, staff confirms, and the order is paid", async ({
    page,
    browser,
  }) => {
    // 1) Shopper checks out with card-to-card and lands on the order confirmation.
    await addFromPdp(page, PRODUCTS.darkRoast.code, dr250.sku);
    await checkoutToReview(page);
    await page.locator('input[type="radio"][value="card_to_card"]').check();
    await page.getByRole("button", { name: checkout.placeOrder }).click();
    await expect(page).toHaveURL(/\/orders\/ORD-/);
    const orderNumber = new URL(page.url()).pathname.split("/").pop() as string;

    // 2) The server-owned destination card is shown (never entered by the buyer), and the
    //    buyer reports their transfer reference.
    await expect(page.getByText(DESTINATION_CARD)).toBeVisible();
    await page.getByLabel(payment.transferReferencePrompt).fill(TRANSFER);
    await page.getByRole("button", { name: payment.submitTransfer }).click();
    await expect(page.getByText(payment.transferAwaitingConfirmation)).toBeVisible();

    // 3) The payment is pending with the reported reference captured server-side.
    const before = await page.request.get(`/api/v1/payments/for-order/${orderNumber}/`);
    expect(before.ok()).toBeTruthy();
    const pending = await before.json();
    expect(pending.status).toBe("pending");
    expect(pending.transfer_reference).toBe(TRANSFER);
    const reference = pending.reference as string;

    // 4) A shopper cannot confirm their own payment (the endpoint is manage_orders-gated).
    const forbidden = await page.request.post(`/api/v1/payments/${reference}/confirm/`);
    expect(forbidden.status()).toBe(403);

    // 5) Staff verify the transfer and confirm it -> captured, order paid.
    const staffContext = await browser.newContext({ storageState: STAFF_STATE });
    const confirmRes = await staffContext.request.post(
      `/api/v1/payments/${reference}/confirm/`,
    );
    expect(confirmRes.status()).toBe(200);
    expect((await confirmRes.json()).status).toBe("captured");
    await staffContext.close();

    // 6) The shopper's order now shows paid.
    await page.reload();
    await expect(page.getByText(orders.statusPaid).first()).toBeVisible();
  });
});

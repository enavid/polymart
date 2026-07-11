/**
 * Wallet + refund-to-wallet, end to end against the real backend.
 *
 * The full money flow: the shopper pays online (captured -> order paid), then a staff member
 * (the only role allowed) refunds the captured payment to the shopper's wallet through the
 * real refund endpoint. The shopper's order then shows the payment as refunded, and the
 * wallet page shows the credited balance and the ledger entry -- the server's exact amount,
 * rendered (never recomputed) in Toman.
 *
 * Runs serially in one worker: it uses the single shared seeded shopper (one wallet, one
 * order history, reset before every run).
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
const wallet = messages.wallet;
const account = messages.account;
const SEED = SHOPPER_ADDRESS.recipientName;
const dr250 = PRODUCTS.darkRoast.variants[0]; // 150,000

function money(amount: number): string {
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

async function checkoutToReview(page: Page): Promise<void> {
  await page.goto("/cart");
  await page.getByRole("link", { name: cart.checkout }).click();
  await expect(page).toHaveURL(/\/checkout/);
  await page.locator("label").filter({ hasText: SEED }).getByRole("radio").check();
  await page.getByRole("button", { name: checkout.continue }).click();
  // Use free shipping so the order total stays the goods amount -- this spec exercises the
  // wallet money flow (fund via refund, spend, debit), not shipping cost.
  await page.locator('input[type="radio"][value="free"]').check();
}

async function payOnline(page: Page): Promise<string> {
  await checkoutToReview(page);
  await page.locator('input[type="radio"][value="online"]').check();
  await page.getByRole("button", { name: checkout.placeOrder }).click();
  await expect(page).toHaveURL(/\/payments\/mock-gateway\//);
  await page.locator("#mock_pay").click();
  await expect(page).toHaveURL(/\/orders\/ORD-/);
  await expect(page.getByText(orders.statusPaid).first()).toBeVisible();
  return new URL(page.url()).pathname.split("/").pop() as string;
}

async function payWithWallet(page: Page): Promise<string> {
  await checkoutToReview(page);
  const walletRadio = page.locator('input[type="radio"][value="wallet"]');
  await expect(walletRadio).toBeEnabled(); // the balance covers the order
  await walletRadio.check();
  await page.getByRole("button", { name: checkout.placeOrder }).click();
  // Wallet payment settles internally (no gateway): straight to the paid order.
  await expect(page).toHaveURL(/\/orders\/ORD-/);
  await expect(page.getByText(orders.statusPaid).first()).toBeVisible();
  return new URL(page.url()).pathname.split("/").pop() as string;
}

test.describe.serial("wallet & refund-to-wallet", () => {
  test("staff refunds a captured payment; the shopper sees wallet credit", async ({
    page,
    browser,
  }) => {
    // 1) Shopper buys DR-250 and pays online -> the payment is captured, order paid.
    await addFromPdp(page, PRODUCTS.darkRoast.code, dr250.sku);
    const orderNumber = await payOnline(page);

    // Resolve the shopper's payment reference (owner-scoped read on their own order).
    const paymentRes = await page.request.get(
      `/api/v1/payments/for-order/${orderNumber}/`,
    );
    expect(paymentRes.ok()).toBeTruthy();
    const reference = (await paymentRes.json()).reference as string;

    // 2) A shopper cannot refund (not staff): the refund endpoint is manage_orders-gated.
    const forbidden = await page.request.post(`/api/v1/payments/${reference}/refund/`);
    expect(forbidden.status()).toBe(403);

    // 3) Staff refunds the captured payment to the shopper's wallet (the real endpoint).
    const staffContext = await browser.newContext({ storageState: STAFF_STATE });
    const refundRes = await staffContext.request.post(
      `/api/v1/payments/${reference}/refund/`,
    );
    expect(refundRes.status()).toBe(200);
    expect((await refundRes.json()).status).toBe("refunded");
    await staffContext.close();

    // 4) The shopper's order now shows the payment as refunded.
    await page.reload();
    await expect(page.getByText(payment.statusRefunded)).toBeVisible();

    // 5) The wallet page shows the credited balance (150,000 IRR -> Toman) and the entry.
    await page.goto("/account/wallet");
    await expect(page.getByTestId("wallet-balance")).toHaveText(money(150000));
    // Scope to the statement cell so the reason word cannot collide with page chrome.
    await expect(page.getByRole("cell", { name: wallet.reasonRefund })).toBeVisible();
  });

  test("the shopper pays a new order from the wallet and sees the debit", async ({ page }) => {
    // The wallet holds 150,000 from the refund in the previous test; spend it on a new order.
    await addFromPdp(page, PRODUCTS.darkRoast.code, dr250.sku);
    const orderNumber = await payWithWallet(page);

    // The payment is a captured wallet payment (settled server-side, never client-computed).
    const paymentRes = await page.request.get(
      `/api/v1/payments/for-order/${orderNumber}/`,
    );
    expect(paymentRes.ok()).toBeTruthy();
    const paid = await paymentRes.json();
    expect(paid.method).toBe("wallet");
    expect(paid.status).toBe("captured");

    // The wallet is now empty and shows the debit entry (150,000 spent -> 0 balance).
    await page.goto("/account/wallet");
    await expect(page.getByTestId("wallet-balance")).toHaveText(money(0));
    // Scope to the statement cell -- the reason word must not collide with page chrome.
    await expect(
      page.getByRole("cell", { name: wallet.reasonOrderPayment }),
    ).toBeVisible();
  });

  test("does not offer pay-with-wallet once the balance is spent", async ({ page }) => {
    // The wallet is empty after the previous test; the option must not be selectable.
    await addFromPdp(page, PRODUCTS.darkRoast.code, dr250.sku);
    await checkoutToReview(page);

    // The method chooser is shown (COD is always available) but wallet is not offered.
    await expect(page.locator('input[type="radio"][value="cod"]')).toBeVisible();
    await expect(page.locator('input[type="radio"][value="wallet"]')).toHaveCount(0);
  });

  test("the account hub links to the wallet", async ({ page }) => {
    await page.goto("/account");
    await page.getByRole("link", { name: account.hubWallet }).click();
    await expect(page).toHaveURL(/\/account\/wallet/);
    await expect(page.getByRole("heading", { name: wallet.title })).toBeVisible();
  });
});

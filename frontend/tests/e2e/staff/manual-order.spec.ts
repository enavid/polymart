/**
 * Manual order + printable pre-invoice, driven as the seeded staff user (order_admin)
 * against the real backend. Staff create an order for a customer from explicit lines and
 * an inline shipping address, then land on the printable pre-invoice showing the exact
 * server-computed totals.
 *
 *   /manage/orders/new -> fill a line + inline address -> submit ->
 *   /manage/orders/<number>/pre-invoice (number, line, grand total, tax placeholder).
 *
 * The manual order is a real pending order that deducts stock, so the spec cancels it at
 * the end (the staff member owns it) to restock -- keeping the shared seeded stock pool
 * pristine regardless of run order.
 */

import { expect, test, type Page } from "@playwright/test";

import { formatCurrency } from "../../../src/lib/format";
import messages from "../../../src/i18n/messages/fa.json";
import { ADDRESS, PRODUCTS } from "../fixtures/seed";

const manual = messages.manualOrder;
const pre = messages.preInvoice;
const orders = messages.orders;
const addresses = messages.addresses;
const hb250 = PRODUCTS.houseBlend.variants[0]; // 120,000

function money(amount: number): string {
  // Delegate to the app's own formatter (its single source of truth) so the E2E
  // assertions render money exactly as the UI does -- IRR presented in Toman.
  return formatCurrency(amount, "IRR");
}

async function fillInlineAddress(page: Page): Promise<void> {
  await page.getByLabel(addresses.recipientName).fill(ADDRESS.recipientName);
  await page.getByLabel(addresses.phoneNumber).fill(ADDRESS.phoneNumber);
  await page.getByLabel(addresses.province).fill(ADDRESS.province);
  await page.getByLabel(addresses.city).fill(ADDRESS.city);
  await page.getByLabel(addresses.postalCode).fill(ADDRESS.postalCode);
  await page.getByLabel(addresses.line1).fill(ADDRESS.line1);
}

test("staff create a manual order and reach its printable pre-invoice", async ({ page }) => {
  // 1) Open the manual-order form (also reachable from the admin nav).
  await page.goto("/manage/orders/new");
  await expect(page.getByRole("heading", { name: manual.title })).toBeVisible();

  // 2) One line: HB-250 x2 (=240,000), plus the customer's inline shipping address.
  await page.getByLabel(manual.sku).fill(hb250.sku);
  await page.getByLabel(manual.quantity).fill("2");
  await fillInlineAddress(page);
  await page.getByRole("button", { name: manual.submit }).click();

  // 3) Lands on the printable pre-invoice with the exact server totals.
  await expect(page).toHaveURL(/\/manage\/orders\/ORD-[A-Z0-9]+\/pre-invoice$/);
  await expect(page.getByRole("heading", { name: pre.title })).toBeVisible();
  await expect(page.getByText(hb250.sku)).toBeVisible();
  await expect(page.getByText(money(240000)).first()).toBeVisible();
  // Tax is a placeholder (computed in a later phase) and a Print control is offered.
  await expect(page.getByText(pre.taxPending)).toBeVisible();
  await expect(page.getByRole("button", { name: pre.print })).toBeVisible();

  // Cleanup: the staff member owns this order, so cancel it (restocks) to keep the
  // shared seeded stock pool pristine for other specs/runs.
  const number = page.url().match(/orders\/(ORD-[A-Z0-9]+)\//)?.[1] as string;
  await page.goto(`/orders/${number}`);
  await page.getByRole("button", { name: orders.cancel }).click();
  await page.getByRole("button", { name: orders.cancel }).click();
  await expect(page.getByText(orders.cancelledNote)).toBeVisible();
});

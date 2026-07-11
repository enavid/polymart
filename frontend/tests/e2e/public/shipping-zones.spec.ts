/**
 * Zoned shipping rates, end to end against the real backend.
 *
 * A method's price depends on where it ships: the dev/test config defines a discounted
 * Tehran zone (standard = 30,000) while every other province pays the default (50,000).
 * This spec proves, against the real stack, that:
 *   - a destination inside the zone is quoted the zoned rate,
 *   - changing the address re-quotes (the chooser refetches for the new province),
 *   - and the placed order captures the rate the server re-resolves from its address
 *     (the displayed money is the server's, never a client recomputation).
 *
 * Runs in the `public` project: each test gets a fresh guest context (fresh cart token), so
 * it starts from a known-empty cart without any per-run seed reset. A guest can enter any
 * inline province, which is exactly what lets one test exercise two different zones.
 */

import { expect, test, type Page } from "@playwright/test";

import { formatCurrency } from "../../../src/lib/format";
import messages from "../../../src/i18n/messages/fa.json";
import { PRODUCTS } from "../fixtures/seed";

const cart = messages.cart;
const store = messages.storefront;
const orders = messages.orders;
const checkout = messages.checkout;
const addresses = messages.addresses;
const dr250 = PRODUCTS.darkRoast.variants[0]; // 150,000, stock 5

// A one-off inline address for whichever province a test wants to ship to. Only the province
// governs the zone; the other fields are just valid form input.
const BASE_ADDRESS = {
  recipientName: "زون تست",
  phoneNumber: "09120000123",
  city: "شهر",
  postalCode: "1234512345",
  line1: "خیابان نمونه، پلاک ۱",
};

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

/** Fill the guest inline shipping form for a given province and submit it to reach review. */
async function fillInlineShipping(page: Page, province: string): Promise<void> {
  await page.getByLabel(addresses.recipientName).fill(BASE_ADDRESS.recipientName);
  await page.getByLabel(addresses.phoneNumber).fill(BASE_ADDRESS.phoneNumber);
  await page.getByLabel(addresses.province).fill(province);
  await page.getByLabel(addresses.city).fill(BASE_ADDRESS.city);
  await page.getByLabel(addresses.postalCode).fill(BASE_ADDRESS.postalCode);
  await page.getByLabel(addresses.line1).fill(BASE_ADDRESS.line1);
  await page.getByRole("button", { name: addresses.save }).click();
}

test("guest: the shipping rate is zoned by province and re-quotes when the address changes", async ({
  page,
}) => {
  // 1) A fresh guest adds one DR-250 (150,000) and reaches checkout.
  await addFromPdp(page, PRODUCTS.darkRoast.code, dr250.sku);
  await page.goto("/cart");
  await page.getByRole("link", { name: cart.checkout }).click();
  await expect(page).toHaveURL(/\/checkout/);

  // 2) Ship to تهران (the discounted zone): standard is quoted at 30,000, so the preview total
  //    is 150,000 + 30,000 = 180,000 (both server values).
  await fillInlineShipping(page, "تهران");
  await page.locator('input[type="radio"][value="standard"]').check();
  await expect(page.getByTestId("checkout-shipping-cost")).toHaveText(money(30000));
  await expect(page.getByTestId("checkout-total")).toHaveText(money(180000));

  // 3) Change the address to اصفهان (outside every zone): the chooser refetches and standard
  //    now costs the default 50,000, re-pricing the total to 200,000. This proves the rate is
  //    re-quoted from the destination, not remembered from the first province.
  await page.getByRole("button", { name: checkout.back }).click();
  await page.getByLabel(addresses.province).fill("اصفهان");
  await page.getByRole("button", { name: addresses.save }).click();
  await page.locator('input[type="radio"][value="standard"]').check();
  await expect(page.getByTestId("checkout-shipping-cost")).toHaveText(money(50000));
  await expect(page.getByTestId("checkout-total")).toHaveText(money(200000));

  // 4) Go back to تهران and place the order: the captured cost is the zoned 30,000, and the
  //    order page shows the breakdown 150,000 / 30,000 / 180,000 -- the server's re-resolved
  //    rate, never the client's.
  await page.getByRole("button", { name: checkout.back }).click();
  await page.getByLabel(addresses.province).fill("تهران");
  await page.getByRole("button", { name: addresses.save }).click();
  await page.locator('input[type="radio"][value="standard"]').check();
  await page.getByRole("button", { name: checkout.placeOrder }).click();

  await expect(page).toHaveURL(/\/orders\/ORD-/);
  const orderNumber = page.url().split("/orders/")[1].replace(/\/$/, "");
  await expect(page.getByText(money(150000)).first()).toBeVisible();
  await expect(page.getByText(money(30000)).first()).toBeVisible();
  await expect(page.getByText(money(180000)).first()).toBeVisible();

  // 5) The server confirms the captured cost is the zoned rate (not the amount last shown for
  //    اصفهان), read back from the guest's own order.
  const orderRes = await page.request.get(`/api/v1/orders/${orderNumber}/`);
  expect(orderRes.ok()).toBeTruthy();
  const order = await orderRes.json();
  expect(order.shipping_cost).toBe("30000.0000");
  expect(order.total).toBe("180000.0000");

  // 6) Clean up: cancel the order so the shared stock pool stays pristine for other specs.
  await page.getByRole("button", { name: orders.cancel }).click();
  await expect(page.getByText(orders.cancelConfirm)).toBeVisible();
  await page.getByRole("button", { name: orders.cancel }).click();
  await expect(page.getByText(orders.statusCancelled).first()).toBeVisible();
});

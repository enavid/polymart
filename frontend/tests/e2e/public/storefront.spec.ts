/**
 * Public storefront (no auth): the home page, the product list (PLP) with its
 * result count / search / view links, and the product detail page (PDP) with its
 * per-channel priced variants. Runs against the real backend + seeded catalog.
 */

import { expect, test } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { PRODUCTS, PUBLISHED_PRODUCT_COUNT } from "../fixtures/seed";

const store = messages.storefront;

/** Reproduce the UI's money formatting so we assert the *displayed* server value. */
function money(amount: number): string {
  return new Intl.NumberFormat("fa-IR", { style: "currency", currency: "IRR" }).format(amount);
}

test("home page links to the storefront and reports backend health", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Polymart" })).toBeVisible();
  // Both the header and the page body link to the storefront; assert the body one.
  await expect(
    page.getByRole("main").getByRole("link", { name: messages.nav.storefront }),
  ).toBeVisible();
  // The home page fetches real backend health; seeded stack is reachable.
  await expect(page.getByTestId("backend-state")).not.toContainText("unreachable");
});

test("PLP lists the seeded published products with a result count", async ({ page }) => {
  await page.goto("/products");

  await expect(page.getByRole("heading", { name: store.title })).toBeVisible();
  await expect(
    page.getByText(store.resultCount.replace("{count}", String(PUBLISHED_PRODUCT_COUNT))),
  ).toBeVisible();

  for (const product of [PRODUCTS.houseBlend, PRODUCTS.darkRoast, PRODUCTS.lightRoast]) {
    await expect(page.getByText(product.name, { exact: true })).toBeVisible();
  }
});

test("PLP search narrows the results to the matching product", async ({ page }) => {
  await page.goto("/products");
  await page.locator("#storefront_search").fill(PRODUCTS.darkRoast.name);
  await page.getByRole("button", { name: store.search }).click();

  await expect(page.getByText(store.resultCount.replace("{count}", "1"))).toBeVisible();
  await expect(page.getByText(PRODUCTS.darkRoast.name, { exact: true })).toBeVisible();
  await expect(page.getByText(PRODUCTS.houseBlend.name, { exact: true })).toHaveCount(0);
});

test("PDP shows a product's variants with their per-channel prices", async ({ page }) => {
  const product = PRODUCTS.houseBlend;
  await page.goto(`/products/${product.code}`);

  await expect(page.getByRole("heading", { name: store.variants })).toBeVisible();
  for (const variant of product.variants) {
    await expect(page.getByText(variant.sku, { exact: true })).toBeVisible();
  }
  // The 250g variant is priced at 120,000 in this channel -- shown as localized money.
  await expect(page.getByText(money(120000))).toBeVisible();
});

test("PDP 'view product' link from the PLP reaches the detail page", async ({ page }) => {
  await page.goto("/products");
  await page.getByRole("link", { name: store.viewProduct }).first().click();

  await expect(page).toHaveURL(/\/products\/[a-z-]+$/);
  await expect(page.getByRole("heading", { name: store.variants })).toBeVisible();
});

/**
 * Public storefront (no auth): the home page, the product list (PLP) with its
 * result count / search / view links, and the product detail page (PDP) with its
 * per-channel priced variants. Runs against the real backend + seeded catalog.
 */

import { expect, test } from "@playwright/test";

import { formatCurrency } from "../../../src/lib/format";
import messages from "../../../src/i18n/messages/fa.json";
import { PRODUCTS, PUBLISHED_PRODUCT_COUNT } from "../fixtures/seed";

const store = messages.storefront;

/** Reproduce the UI's money formatting so we assert the *displayed* server value. */
function money(amount: number): string {
  // Delegate to the app's own formatter (its single source of truth) so the E2E
  // assertions render money exactly as the UI does -- IRR presented in Toman.
  return formatCurrency(amount, "IRR");
}

test("home page shows the hero, a shop CTA, and featured products", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: messages.home.heroTitle })).toBeVisible();
  // The hero call-to-action links into the storefront.
  const cta = page.getByRole("main").getByRole("link", { name: messages.home.shopCta });
  await expect(cta).toBeVisible();
  await expect(cta).toHaveAttribute("href", "/products");
  // The featured strip pulls real published products from the storefront read API.
  await expect(page.getByText(messages.home.featuredTitle)).toBeVisible();
  await expect(page.getByText(PRODUCTS.houseBlend.name, { exact: true }).first()).toBeVisible();
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

  // Each card shows a "from" price for the channel (house-blend's cheapest
  // variant is 120,000), and the out-of-stock product (light-roast) is flagged.
  await expect(page.getByText(store.priceFrom.replace("{price}", money(120000)))).toBeVisible();
  await expect(page.getByText(store.outOfStock)).toBeVisible();
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
  // The PDP renders the seeded product description (metadata), not just variants.
  await expect(page.getByText(product.description)).toBeVisible();
});

test("PDP 'view product' link from the PLP reaches the detail page", async ({ page }) => {
  await page.goto("/products");
  await page.getByRole("link", { name: store.viewProduct }).first().click();

  await expect(page).toHaveURL(/\/products\/[a-z-]+$/);
  await expect(page.getByRole("heading", { name: store.variants })).toBeVisible();
});

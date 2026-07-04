/**
 * The catalog admin area, driven as the seeded staff user against the real
 * backend. Covers every catalog admin route -- the list managers and the
 * product / variant / collection detail pages -- asserting each renders with its
 * seeded data. Read-only, so the specs are safe to run in parallel.
 */

import { expect, test } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { CATEGORY, COLLECTION, PRODUCTS, PRODUCT_TYPE_CODE } from "../fixtures/seed";

const catalog = messages.catalog;

test("/manage/catalog redirects to the products manager", async ({ page }) => {
  await page.goto("/manage/catalog");
  await expect(page).toHaveURL(/\/manage\/catalog\/products$/);
  await expect(page.getByRole("heading", { name: catalog.products.title })).toBeVisible();
});

test("products manager lists the seeded products", async ({ page }) => {
  await page.goto("/manage/catalog/products");
  for (const product of [PRODUCTS.houseBlend, PRODUCTS.darkRoast, PRODUCTS.lightRoast]) {
    await expect(page.getByText(product.code, { exact: true })).toBeVisible();
    await expect(page.getByText(product.name, { exact: true })).toBeVisible();
  }
});

test("product-types manager lists the seeded type", async ({ page }) => {
  await page.goto("/manage/catalog/product-types");
  await expect(page.getByRole("heading", { name: catalog.productTypes.title })).toBeVisible();
  await expect(page.getByText(PRODUCT_TYPE_CODE, { exact: true })).toBeVisible();
});

test("attributes manager renders", async ({ page }) => {
  await page.goto("/manage/catalog/attributes");
  await expect(page.getByRole("heading", { name: catalog.attributes.title })).toBeVisible();
});

test("categories manager lists the seeded category tree", async ({ page }) => {
  await page.goto("/manage/catalog/categories");
  await expect(page.getByRole("heading", { name: catalog.categories.title })).toBeVisible();
  // The slug appears in both the parent-select and the table; assert the table cell.
  await expect(page.getByRole("cell", { name: CATEGORY.root, exact: true }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: CATEGORY.child, exact: true }).first()).toBeVisible();
});

test("collections manager lists the seeded collection", async ({ page }) => {
  await page.goto("/manage/catalog/collections");
  await expect(page.getByRole("heading", { name: catalog.collections.title })).toBeVisible();
  await expect(page.getByText(COLLECTION, { exact: true })).toBeVisible();
});

test("import/export page renders", async ({ page }) => {
  await page.goto("/manage/catalog/import-export");
  await expect(page.getByRole("heading", { name: catalog.importExport.title })).toBeVisible();
});

test("product detail page shows the product and its variants", async ({ page }) => {
  const product = PRODUCTS.houseBlend;
  await page.goto(`/manage/catalog/products/${product.code}`);
  // The name shows as both the page heading and a definition row; either proves it.
  await expect(page.getByText(product.name, { exact: true }).first()).toBeVisible();
  for (const variant of product.variants) {
    await expect(page.getByText(variant.sku, { exact: true })).toBeVisible();
  }
});

test("variant detail page shows the variant, its price and stock", async ({ page }) => {
  const variant = PRODUCTS.houseBlend.variants[0]; // HB-250
  await page.goto(`/manage/catalog/variants/${variant.sku}`);
  await expect(page.getByText(variant.sku, { exact: true })).toBeVisible();
  // The prices card lists the per-channel price for this variant.
  await expect(page.getByText("ir-main").first()).toBeVisible();
});

test("collection detail page shows the collection and its members", async ({ page }) => {
  await page.goto(`/manage/catalog/collections/${COLLECTION}`);
  await expect(page.getByRole("heading", { name: COLLECTION })).toBeVisible();
  // Membership is shown as a comma-joined value in the members field.
  await expect(page.locator("#collection_members")).toHaveValue(
    new RegExp(PRODUCTS.houseBlend.code),
  );
});

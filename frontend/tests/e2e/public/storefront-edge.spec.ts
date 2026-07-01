/**
 * Rigorous storefront edge cases (public): an empty search result, a
 * discriminating collection filter, pagination boundaries, and a variant that is
 * unavailable in the storefront's channel (priced only elsewhere).
 */

import { expect, test } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { COLLECTION, PRODUCTS, UNAVAILABLE_VARIANT } from "../fixtures/seed";

const store = messages.storefront;

test("search with no matches shows the empty state", async ({ page }) => {
  await page.goto("/products");
  await page.locator("#storefront_search").fill("no-such-product-xyz");
  await page.getByRole("button", { name: store.search }).click();

  await expect(page.getByText(store.resultCount.replace("{count}", "0"))).toBeVisible();
  await expect(page.getByText(store.empty)).toBeVisible();
});

test("collection filter narrows to the collection's members only", async ({ page }) => {
  await page.goto("/products");
  // The "featured" collection has house-blend + dark-roast, but not light-roast.
  await page.locator("#storefront_collection").fill(COLLECTION);
  await page.getByRole("button", { name: store.search }).click();

  await expect(page.getByText(store.resultCount.replace("{count}", "2"))).toBeVisible();
  await expect(page.getByText(PRODUCTS.houseBlend.name, { exact: true })).toBeVisible();
  await expect(page.getByText(PRODUCTS.lightRoast.name, { exact: true })).toHaveCount(0);
});

test("pagination previous is disabled on the first page", async ({ page }) => {
  await page.goto("/products");
  await expect(page.getByText(store.resultCount.replace("{count}", "3"))).toBeVisible();
  await expect(page.getByRole("button", { name: store.previous })).toBeDisabled();
});

test("a variant unavailable in this channel is shown unavailable with no add control", async ({
  page,
}) => {
  await page.goto(`/products/${UNAVAILABLE_VARIANT.productCode}`);
  await expect(page.getByText(UNAVAILABLE_VARIANT.sku, { exact: true })).toBeVisible();
  // Its price cell reads "unavailable in this channel"...
  await expect(page.getByText(store.unavailable)).toBeVisible();
  // ...and no quantity input / add-to-cart control is rendered for it.
  await expect(page.locator(`#variant_qty_${UNAVAILABLE_VARIANT.sku}`)).toHaveCount(0);
});

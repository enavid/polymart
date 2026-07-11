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
  // Search drives the PLP through `?q=`; the result count is hidden when there are
  // no matches, so the empty state is the assertion.
  await page.goto("/products?q=no-such-product-xyz");

  await expect(page.getByText(store.empty)).toBeVisible();
});

test("collection filter narrows to the collection's members only", async ({ page }) => {
  await page.goto("/products");
  // The "featured" collection has house-blend + dark-roast, but not light-roast.
  // The filter is a sidebar dropdown; the choice takes effect via «اعمال فیلترها».
  await page.locator("#storefront_collection").selectOption(COLLECTION);
  await page.getByRole("button", { name: store.applyFilters }).click();

  await expect(page.getByText(store.resultCount.replace("{count}", "2"))).toBeVisible();
  await expect(page.getByText(PRODUCTS.houseBlend.name, { exact: true })).toBeVisible();
  await expect(page.getByText(PRODUCTS.lightRoast.name, { exact: true })).toHaveCount(0);
});

test("pagination controls are hidden when the results fit a single page", async ({ page }) => {
  await page.goto("/products");
  await expect(page.getByText(store.resultCount.replace("{count}", "3"))).toBeVisible();
  // The numbered pagination only appears when there is more than one page; the
  // seeded catalog (3 products) fits one page, so there are no prev/next controls.
  await expect(page.getByRole("button", { name: store.previous })).toHaveCount(0);
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

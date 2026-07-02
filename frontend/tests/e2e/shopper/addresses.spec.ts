/**
 * The authenticated shopper's address book, end to end against the real backend.
 * Like the cart/checkout journey, the seeded shopper's saved addresses are one shared
 * resource (reset to empty by `seed_e2e` before every run), so these run **serially in
 * one worker** -- parallel tests would race on that shared state.
 *
 *   book:      empty -> add first (becomes default) -> add second (not default) ->
 *              set second as default (swaps exclusively) -> edit (default untouched) ->
 *              delete via inline confirmation (no browser dialog).
 *   boundary:  an invalid postal code is rejected with a validation message, nothing
 *              is created; the per-owner cap (20) is enforced with a conflict, and the
 *              21st address is refused.
 *   ownership: a different account (staff) never sees the shopper's saved addresses.
 */

import { expect, test, type Locator, type Page } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { ADDRESS, ADDRESS_LIMIT, STAFF_STATE } from "../fixtures/seed";

const addresses = messages.addresses;

/**
 * Navigate to the address book and wait for the list to settle into either its empty
 * state or at least one rendered card, so a subsequent `.count()` (which does not
 * auto-retry, unlike `expect(...)`) reads the committed DOM instead of racing the
 * initial fetch/render.
 */
async function gotoAddresses(page: Page): Promise<void> {
  await page.goto("/addresses");
  await page.getByText(addresses.empty).or(page.getByTestId("address-card").first()).waitFor();
}

/** The card for the address with the given recipient name (there is exactly one). */
function cardFor(page: Page, recipientName: string): Locator {
  return page.getByTestId("address-card").filter({ hasText: recipientName });
}

async function fillAddressForm(page: Page, overrides: Partial<typeof ADDRESS> = {}): Promise<void> {
  const values = { ...ADDRESS, ...overrides };
  await page.getByLabel(addresses.recipientName).fill(values.recipientName);
  await page.getByLabel(addresses.phoneNumber).fill(values.phoneNumber);
  await page.getByLabel(addresses.province).fill(values.province);
  await page.getByLabel(addresses.city).fill(values.city);
  await page.getByLabel(addresses.postalCode).fill(values.postalCode);
  await page.getByLabel(addresses.line1).fill(values.line1);
}

/** Open the add form, fill it, save, and wait for the form to close back to the list. */
async function addAddress(page: Page, overrides: Partial<typeof ADDRESS> = {}): Promise<void> {
  await page.getByRole("button", { name: addresses.addNew }).click();
  await fillAddressForm(page, overrides);
  await page.getByRole("button", { name: addresses.save }).click();
  await expect(page.getByRole("button", { name: addresses.addNew })).toBeVisible();
}

/** Open the add form, fill it, save, and expect it to be rejected (form stays open). */
async function addAddressExpectingError(
  page: Page,
  errorMessage: string,
  overrides: Partial<typeof ADDRESS> = {},
): Promise<void> {
  await page.getByRole("button", { name: addresses.addNew }).click();
  await fillAddressForm(page, overrides);
  await page.getByRole("button", { name: addresses.save }).click();
  await expect(page.getByText(errorMessage)).toBeVisible();
  await page.getByRole("button", { name: addresses.cancel }).click();
}

/** Delete every saved address via the inline confirm (never a browser dialog). */
async function deleteAllAddresses(page: Page): Promise<void> {
  await gotoAddresses(page);
  // gotoAddresses already waited for the list to settle, so this first read is
  // accurate; each iteration below re-verifies the new count with an auto-retrying
  // `expect` (the delete mutation's refetch is async, so a raw `.count()` right
  // after clicking would race it).
  let remaining = await page.getByTestId("address-card").count();
  while (remaining > 0) {
    await page.getByRole("button", { name: addresses.delete }).first().click();
    await expect(page.getByText(addresses.deleteConfirm)).toBeVisible();
    await page.getByRole("button", { name: addresses.delete }).first().click();
    remaining -= 1;
    await expect(page.getByTestId("address-card")).toHaveCount(remaining);
  }
  await expect(page.getByText(addresses.empty)).toBeVisible();
}

test.describe.serial("shopper address book", () => {
  test("book: empty, add the first (default), add a second (not default)", async ({ page }) => {
    await gotoAddresses(page);
    await expect(page.getByText(addresses.empty)).toBeVisible();

    await addAddress(page);
    await expect(
      cardFor(page, ADDRESS.recipientName).getByText(addresses.default, { exact: true }),
    ).toBeVisible();

    await addAddress(page, { recipientName: "Reza Karimi", city: "Shiraz" });
    await expect(page.getByTestId("address-card")).toHaveCount(2);
    // Only the first address is default; the second is not.
    await expect(page.getByText(addresses.default, { exact: true })).toHaveCount(1);
    await expect(
      cardFor(page, "Reza Karimi").getByText(addresses.default, { exact: true }),
    ).toHaveCount(0);
  });

  test("book: setting the non-default address as default swaps exclusively", async ({ page }) => {
    await gotoAddresses(page);

    await cardFor(page, "Reza Karimi").getByRole("button", { name: addresses.setDefault }).click();

    // Exactly one address is ever default, and it is now Reza Karimi's.
    await expect(page.getByText(addresses.default, { exact: true })).toHaveCount(1);
    await expect(
      cardFor(page, "Reza Karimi").getByText(addresses.default, { exact: true }),
    ).toBeVisible();
    await expect(
      cardFor(page, ADDRESS.recipientName).getByText(addresses.default, { exact: true }),
    ).toHaveCount(0);
  });

  test("book: editing an address changes its details but never its default status", async ({
    page,
  }) => {
    await gotoAddresses(page);

    await cardFor(page, ADDRESS.recipientName)
      .getByRole("button", { name: addresses.edit })
      .click();
    await expect(page.getByLabel(addresses.recipientName)).toHaveValue(ADDRESS.recipientName);
    await page.getByLabel(addresses.city).fill("Isfahan");
    await page.getByRole("button", { name: addresses.save }).click();

    await expect(cardFor(page, ADDRESS.recipientName).getByText("Tehran، Isfahan")).toBeVisible();
    // Reza Karimi is still the sole default; editing Sara's address did not touch it.
    await expect(page.getByText(addresses.default, { exact: true })).toHaveCount(1);
    await expect(
      cardFor(page, "Reza Karimi").getByText(addresses.default, { exact: true }),
    ).toBeVisible();
  });

  test("boundary: an invalid postal code is rejected without creating an address", async ({
    page,
  }) => {
    await gotoAddresses(page);
    // Two addresses (Sara, Reza) are on the books from the previous test.
    await expect(page.getByTestId("address-card")).toHaveCount(2);

    await addAddressExpectingError(page, addresses.validationError, { postalCode: "123" });

    await expect(page.getByTestId("address-card")).toHaveCount(2);
  });

  test("book: deleting an address requires inline confirmation, not a browser dialog", async ({
    page,
  }) => {
    await gotoAddresses(page);
    // Two addresses (Sara, Reza) are on the books from the previous tests.
    await expect(page.getByTestId("address-card")).toHaveCount(2);
    const rezaCard = cardFor(page, "Reza Karimi");

    await rezaCard.getByRole("button", { name: addresses.delete }).click();
    await expect(page.getByText(addresses.deleteConfirm)).toBeVisible();
    // Cancelling the confirmation leaves the address in place.
    await page.getByRole("button", { name: addresses.cancel }).click();
    await expect(cardFor(page, "Reza Karimi")).toHaveCount(1);

    await rezaCard.getByRole("button", { name: addresses.delete }).click();
    await rezaCard.getByRole("button", { name: addresses.delete }).click();

    await expect(cardFor(page, "Reza Karimi")).toHaveCount(0);
    await expect(page.getByTestId("address-card")).toHaveCount(1);
  });

  test("boundary: a shopper cannot save more than the per-owner limit", async ({ page }) => {
    await deleteAllAddresses(page);

    for (let i = 0; i < ADDRESS_LIMIT; i++) {
      await addAddress(page, { city: `City ${i}` });
    }
    await expect(page.getByTestId("address-card")).toHaveCount(ADDRESS_LIMIT);

    // The 21st address is refused with the limit-exceeded conflict, not created.
    await addAddressExpectingError(page, addresses.limitExceeded);
    await expect(page.getByTestId("address-card")).toHaveCount(ADDRESS_LIMIT);

    // Clean up so a later run starts from an empty address book again.
    await deleteAllAddresses(page);
  });

  test("ownership: a different account never sees the shopper's saved addresses", async ({
    browser,
  }) => {
    const staffContext = await browser.newContext({ storageState: STAFF_STATE });
    const staffPage = await staffContext.newPage();
    await staffPage.goto("/addresses");

    // The staff account has never saved an address of its own -- if the list were
    // not owner-scoped, the shopper's data seeded/added by earlier tests would leak
    // in here.
    await expect(staffPage.getByText(addresses.empty)).toBeVisible();
    await expect(staffPage.getByTestId("address-card")).toHaveCount(0);

    await staffContext.close();
  });
});

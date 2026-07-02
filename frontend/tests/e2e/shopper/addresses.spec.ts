/**
 * The authenticated shopper's address book, end to end against the real backend.
 *
 * The seeded shopper starts each run with exactly one address: the persistent default
 * "home" address (`SHOPPER_ADDRESS`) that `seed_e2e` writes and that checkout ships to.
 * This spec works *relative to that baseline* and **never deletes the seeded address**,
 * so it can run alongside the checkout spec (which targets the seeded address) without
 * racing on a shared, deleted address. These run serially in one worker.
 *
 *   book:      baseline (1, default) -> add a second (not default) -> set it default
 *              (swaps exclusively) -> restore the seed as default -> edit -> delete it.
 *   boundary:  an invalid postal code is rejected; the per-owner cap (20) is enforced
 *              and the 21st address is refused.
 *   ownership: a different account (staff) never sees the shopper's saved addresses.
 */

import { expect, test, type Locator, type Page } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { ADDRESS, ADDRESS_LIMIT, SHOPPER_ADDRESS, STAFF_STATE } from "../fixtures/seed";

const addresses = messages.addresses;
const SEED = SHOPPER_ADDRESS.recipientName;
const SECOND = "Reza Karimi";

/** Navigate to the address book and wait for the seeded card to render. */
async function gotoAddresses(page: Page): Promise<void> {
  await page.goto("/addresses");
  await page.getByTestId("address-card").first().waitFor();
}

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

/** Delete every card **except** the seeded address, leaving the book at its baseline. */
async function resetToBaseline(page: Page): Promise<void> {
  await gotoAddresses(page);
  let count = await page.getByTestId("address-card").count();
  while (count > 1) {
    // Delete the first non-seed card.
    const target = page.getByTestId("address-card").filter({ hasNotText: SEED }).first();
    await target.getByRole("button", { name: addresses.delete }).click();
    await target.getByRole("button", { name: addresses.delete }).click();
    count -= 1;
    await expect(page.getByTestId("address-card")).toHaveCount(count);
  }
  await expect(cardFor(page, SEED)).toHaveCount(1);
}

test.describe.serial("shopper address book", () => {
  test("book: the seeded default is shown, and a new address is not default", async ({ page }) => {
    await gotoAddresses(page);
    await expect(cardFor(page, SEED).getByText(addresses.default, { exact: true })).toBeVisible();
    await expect(page.getByTestId("address-card")).toHaveCount(1);

    await addAddress(page, { recipientName: SECOND, city: "Shiraz" });
    await expect(page.getByTestId("address-card")).toHaveCount(2);
    // Only the seeded address is default; the new one is not.
    await expect(page.getByText(addresses.default, { exact: true })).toHaveCount(1);
    await expect(cardFor(page, SECOND).getByText(addresses.default, { exact: true })).toHaveCount(
      0,
    );
  });

  test("book: setting a non-default address as default swaps exclusively", async ({ page }) => {
    await gotoAddresses(page);

    await cardFor(page, SECOND).getByRole("button", { name: addresses.setDefault }).click();

    // Exactly one address is ever default, and it is now the new one.
    await expect(page.getByText(addresses.default, { exact: true })).toHaveCount(1);
    await expect(cardFor(page, SECOND).getByText(addresses.default, { exact: true })).toBeVisible();
    await expect(cardFor(page, SEED).getByText(addresses.default, { exact: true })).toHaveCount(0);

    // Restore the seed as the default so the checkout spec's preselect stays stable.
    await cardFor(page, SEED).getByRole("button", { name: addresses.setDefault }).click();
    await expect(cardFor(page, SEED).getByText(addresses.default, { exact: true })).toBeVisible();
  });

  test("book: editing an address changes its details but never its default status", async ({
    page,
  }) => {
    await gotoAddresses(page);

    await cardFor(page, SECOND).getByRole("button", { name: addresses.edit }).click();
    await expect(page.getByLabel(addresses.recipientName)).toHaveValue(SECOND);
    await page.getByLabel(addresses.city).fill("Isfahan");
    await page.getByRole("button", { name: addresses.save }).click();

    await expect(cardFor(page, SECOND).getByText("Tehran، Isfahan")).toBeVisible();
    // The seed is still the sole default; editing the other address did not touch it.
    await expect(page.getByText(addresses.default, { exact: true })).toHaveCount(1);
    await expect(cardFor(page, SEED).getByText(addresses.default, { exact: true })).toBeVisible();
  });

  test("boundary: an invalid postal code is rejected without creating an address", async ({
    page,
  }) => {
    await gotoAddresses(page);
    await expect(page.getByTestId("address-card")).toHaveCount(2);

    await addAddressExpectingError(page, addresses.validationError, { postalCode: "123" });

    await expect(page.getByTestId("address-card")).toHaveCount(2);
  });

  test("book: deleting an address requires inline confirmation, not a browser dialog", async ({
    page,
  }) => {
    await gotoAddresses(page);
    await expect(page.getByTestId("address-card")).toHaveCount(2);
    const secondCard = cardFor(page, SECOND);

    await secondCard.getByRole("button", { name: addresses.delete }).click();
    await expect(page.getByText(addresses.deleteConfirm)).toBeVisible();
    // Cancelling the confirmation leaves the address in place.
    await page.getByRole("button", { name: addresses.cancel }).click();
    await expect(cardFor(page, SECOND)).toHaveCount(1);

    await secondCard.getByRole("button", { name: addresses.delete }).click();
    await secondCard.getByRole("button", { name: addresses.delete }).click();

    // Back to the seeded baseline; the seed itself is never deleted.
    await expect(cardFor(page, SECOND)).toHaveCount(0);
    await expect(cardFor(page, SEED)).toHaveCount(1);
  });

  test("boundary: a shopper cannot save more than the per-owner limit", async ({ page }) => {
    await resetToBaseline(page);

    // The seed already occupies one slot; fill the rest up to the cap.
    for (let i = 0; i < ADDRESS_LIMIT - 1; i++) {
      await addAddress(page, { recipientName: SECOND, city: `City ${i}` });
    }
    await expect(page.getByTestId("address-card")).toHaveCount(ADDRESS_LIMIT);

    // The 21st address is refused with the limit-exceeded conflict, not created.
    await addAddressExpectingError(page, addresses.limitExceeded);
    await expect(page.getByTestId("address-card")).toHaveCount(ADDRESS_LIMIT);

    // Clean up the added addresses so a later run/spec starts from the baseline.
    await resetToBaseline(page);
  });

  test("ownership: a different account never sees the shopper's saved addresses", async ({
    browser,
  }) => {
    const staffContext = await browser.newContext({ storageState: STAFF_STATE });
    const staffPage = await staffContext.newPage();
    await staffPage.goto("/addresses");

    // The staff account has never saved an address of its own -- if the list were not
    // owner-scoped, the shopper's seeded/added addresses would leak in here.
    await expect(staffPage.getByText(addresses.empty)).toBeVisible();
    await expect(staffPage.getByTestId("address-card")).toHaveCount(0);
    await expect(staffPage.getByText(SEED)).toHaveCount(0);

    await staffContext.close();
  });
});

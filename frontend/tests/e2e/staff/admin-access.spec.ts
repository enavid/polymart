/**
 * The access/channels/audit admin area, driven as the seeded staff user (who
 * holds the access, channel, and catalog admin roles). Each page is loaded
 * against the real backend and asserted to render with its seeded data.
 */

import { expect, test } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";
import { CHANNEL, CURRENCY } from "../fixtures/seed";

test("/manage renders the admin dashboard", async ({ page }) => {
  await page.goto("/manage");
  // `/manage` is now the dashboard hub (KPIs + quick links), not a redirect.
  await expect(page).toHaveURL(/\/manage$/);
  await expect(page.getByRole("heading", { name: messages.admin.dashboard })).toBeVisible();
});

test("access panel renders the role-assignment and channel-grant forms", async ({ page }) => {
  await page.goto("/manage/access");
  await expect(page.getByRole("heading", { name: messages.admin.assignRoleTitle })).toBeVisible();
  await expect(page.getByRole("heading", { name: messages.admin.grantChannelTitle })).toBeVisible();
});

test("channels admin lists the seeded channel", async ({ page }) => {
  await page.goto("/manage/channels");
  await expect(page.getByRole("heading", { name: messages.channels.title })).toBeVisible();
  await expect(page.getByText(CHANNEL, { exact: true })).toBeVisible();
  await expect(page.getByText(CURRENCY, { exact: true })).toBeVisible();
});

test("audit viewer renders (RBAC events were recorded during seeding)", async ({ page }) => {
  await page.goto("/manage/audit");
  await expect(page.getByRole("heading", { name: messages.audit.title })).toBeVisible();
  // The audit table header is present whether or not rows are shown.
  await expect(page.getByText(messages.audit.action, { exact: true })).toBeVisible();
});

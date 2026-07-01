/**
 * Public auth screens against the real backend: a rejected login, and the OTP
 * *request* step of registration and password reset.
 *
 * The full OTP-verify path (submitting the 6-digit code) is not driven here: in
 * DEBUG the code is only emitted to the backend log and stored as a one-way hash,
 * so a browser test cannot read it back. That verification path is covered by the
 * backend integration tests; here we assert the real request path the UI drives.
 */

import { expect, test } from "@playwright/test";

import messages from "../../../src/i18n/messages/fa.json";

const auth = messages.auth;

/** A fresh, unused Iranian mobile number, so the OTP request never hits a cooldown. */
function freshPhone(): string {
  return "0912" + String(Date.now()).slice(-7);
}

test("login with a wrong password shows the invalid-credentials error", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("شمارهٔ موبایل").fill("09120000001");
  await page.getByLabel("رمز عبور").fill("definitely-wrong");
  await page.getByRole("button", { name: "ورود" }).click();

  await expect(page.getByText(auth.invalidCredentials)).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test("registration page requests an OTP for a phone number", async ({ page }) => {
  await page.goto("/register");
  await expect(page.getByRole("heading", { name: auth.registerTitle })).toBeVisible();

  await page.locator("#phone_number").fill(freshPhone());
  await page.getByRole("button", { name: auth.otpCta }).click();

  await expect(page.getByText(auth.otpSent)).toBeVisible();
});

test("password-reset page requests an OTP for a phone number", async ({ page }) => {
  await page.goto("/password-reset");
  await expect(page.getByRole("heading", { name: auth.resetTitle })).toBeVisible();

  await page.locator("#phone_number").fill(freshPhone());
  await page.getByRole("button", { name: auth.otpCta }).click();

  await expect(page.getByText(auth.otpSent)).toBeVisible();
});

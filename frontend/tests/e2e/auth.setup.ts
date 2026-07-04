/**
 * Authentication setup: log the seeded users in through the real UI and save
 * their browser storage state (the HttpOnly cookie-JWT session) to disk. The
 * `shopper` and `staff` projects reuse these states so their specs start
 * already authenticated, without repeating the login in every test.
 *
 * This runs as a Playwright *setup project* the other projects depend on, so it
 * always executes first. It exercises the genuine login path against the live
 * backend -- there is no mock here.
 */

import { test as setup, expect, type Page } from "@playwright/test";

import { SHOPPER, SHOPPER_STATE, STAFF, STAFF_STATE } from "./fixtures/seed";

async function logIn(page: Page, phone: string, password: string, canonicalPhone: string) {
  // Login returns the user to the captured `next` page (default: home). Ask to
  // return to /account so the session-established assertion below is deterministic.
  await page.goto("/login?next=/account");
  await page.getByLabel("شمارهٔ موبایل").fill(phone);
  await page.getByLabel("رمز عبور").fill(password);
  await page.getByRole("button", { name: "ورود" }).click();

  // A successful login redirects to the requested page and shows the canonical
  // phone -- proof the real cookie session is established.
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByText(canonicalPhone)).toBeVisible();
}

setup("authenticate as shopper", async ({ page }) => {
  await logIn(page, SHOPPER.phone, SHOPPER.password, SHOPPER.canonicalPhone);
  await page.context().storageState({ path: SHOPPER_STATE });
});

setup("authenticate as staff", async ({ page }) => {
  await logIn(page, STAFF.phone, STAFF.password, STAFF.canonicalPhone);
  await page.context().storageState({ path: STAFF_STATE });
});

// The dev server JIT-compiles each route on its first visit, which can take
// several seconds and make the first spec to touch a route flake. Compilation is
// process-global, so visiting the heavier (client-query) routes once here warms
// them for every worker. Every project depends on this setup, so warming runs
// first. (Auth pages are hit as the staff session, which simply ignores them.)
const WARM_ROUTES = [
  "/products",
  "/products/house-blend",
  "/cart",
  "/checkout",
  "/account",
  "/addresses",
  "/orders",
  // A dummy order number compiles the dynamic order route (it renders "not found",
  // but the route is now warm for the checkout/guest specs that land on a real one).
  "/orders/ORD-WARMUP0000",
  "/admin/catalog/products",
  "/admin/catalog/products/house-blend",
  "/admin/catalog/variants/HB-250",
  "/admin/catalog/collections/featured",
  "/admin/catalog/categories",
  "/admin/catalog/collections",
  "/admin/access",
  "/admin/channels",
  "/admin/audit",
  "/admin/orders/new",
  // A dummy pre-invoice route: 404s (no such order), but the dynamic route is now
  // compiled before the manual-order spec lands on a real one.
  "/admin/orders/ORD-WARMUP0000/pre-invoice",
];

setup("warm up routes so the dev server has compiled them", async ({ page }) => {
  // Compiling every route cold, one after another, easily exceeds the 30s default test
  // timeout (each first hit is a full webpack compile), and this primer asserts nothing
  // -- so give it room proportional to the route count. If it times out here, the real
  // specs pay the cold-compile cost instead and flake. A per-goto ceiling keeps a single
  // stuck route from consuming the whole budget.
  setup.setTimeout(180_000);
  for (const route of WARM_ROUTES) {
    await page.goto(route, { waitUntil: "domcontentloaded", timeout: 60_000 });
  }
});

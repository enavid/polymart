import { defineConfig, devices } from "@playwright/test";

import { SHOPPER_STATE, STAFF_STATE } from "./tests/e2e/fixtures/seed";

/**
 * Full-stack E2E configuration. The suite drives the real Next.js storefront
 * against the real Django backend (which must be running and seeded via
 * `python manage.py seed_e2e` -- `make e2e-full` does the whole orchestration).
 *
 * Projects:
 *  - `setup`   logs the seeded users in and saves their cookie sessions.
 *  - `public`  unauthenticated pages (home, storefront, the auth screens).
 *  - `shopper` runs as the seeded shopper (reuses the saved session).
 *  - `staff`   runs as the seeded staff/admin user (reuses the saved session).
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  // A single worker across the whole suite. The money-mutating shopper specs
  // (cart, wallet, card-to-card, guest-cart-merge) all authenticate as the *one*
  // seeded shopper and mutate that shopper's shared cart/wallet; run on separate
  // workers in parallel they contend on the same account and fail
  // non-deterministically. `fullyParallel` still orders tests within a file, but
  // only a single worker prevents cross-file collisions on the shared fixture.
  workers: 1,
  forbidOnly: !!process.env.CI,
  // One retry even locally: the dev server JIT-compiles each route on its first
  // hit, so a cold navigation can momentarily exceed the timeout. A retry lands
  // on the now-warm route; a genuine failure still fails both attempts.
  retries: process.env.CI ? 2 : 1,
  reporter: "list",
  // A full-stack journey (build a cart, check out, reach the order, cancel) makes many
  // navigations, each JIT-compiled by the Next.js dev server, so the longest specs can
  // exceed Playwright's 30s default. Give every test more room; a genuine hang still
  // fails here, and the per-expect ceiling below keeps individual assertions tight.
  timeout: 60_000,
  // A little headroom over the 5s default so a cold route compile does not flake.
  expect: { timeout: 10_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "public",
      testMatch: /public\/.*\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
      dependencies: ["setup"],
    },
    {
      name: "shopper",
      testMatch: /shopper\/.*\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], storageState: SHOPPER_STATE },
      dependencies: ["setup"],
    },
    {
      name: "staff",
      testMatch: /staff\/.*\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], storageState: STAFF_STATE },
      dependencies: ["setup"],
    },
  ],
});

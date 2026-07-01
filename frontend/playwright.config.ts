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
  forbidOnly: !!process.env.CI,
  // One retry even locally: the dev server JIT-compiles each route on its first
  // hit, so a cold navigation can momentarily exceed the timeout. A retry lands
  // on the now-warm route; a genuine failure still fails both attempts.
  retries: process.env.CI ? 2 : 1,
  reporter: "list",
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

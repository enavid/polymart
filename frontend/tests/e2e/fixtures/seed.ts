/**
 * The deterministic dataset the E2E suite runs against.
 *
 * This mirrors the backend seed command
 * `backend/src/infrastructure/devtools/management/commands/seed_e2e.py`. The two
 * MUST stay in sync -- these are the same users, channel, and catalog the
 * command writes, expressed for the browser tests that assert against them.
 */

export const CHANNEL = "ir-main";
export const CURRENCY = "IRR";

export const SHOPPER = {
  phone: "09120000001",
  password: "shopper-pass-123",
  // Login normalises the phone to canonical E.164; the account page shows this.
  canonicalPhone: "+989120000001",
  fullName: "Shopper",
};

export const STAFF = {
  phone: "09120000009",
  password: "staff-pass-123",
  canonicalPhone: "+989120000009",
  fullName: "Staff",
};

export const PRODUCTS = {
  houseBlend: {
    code: "house-blend",
    name: "House Blend",
    variants: [
      { sku: "HB-250", name: "250g", price: "120000.0000" as string | null },
      { sku: "HB-500", name: "500g", price: "200000.0000" as string | null },
      // Priced only in another channel -> unavailable (not purchasable) here.
      { sku: "HB-1000", name: "1kg", price: null as string | null },
    ],
  },
  darkRoast: {
    code: "dark-roast",
    name: "Dark Roast",
    variants: [{ sku: "DR-250", name: "250g", price: "150000.0000" }],
  },
  lightRoast: {
    code: "light-roast",
    name: "Light Roast",
    variants: [{ sku: "LR-250", name: "250g", price: "100000.0000" }],
  },
} as const;

export const PUBLISHED_PRODUCT_COUNT = 3;

/** A variant that is priced only in another channel, so it is unavailable here. */
export const UNAVAILABLE_VARIANT = { sku: "HB-1000", productCode: "house-blend" };

export const PRODUCT_TYPE_CODE = "coffee";
export const CATEGORY = { root: "hot-drinks", child: "coffee-beans" };
export const COLLECTION = "featured";

/** Where the saved auth storage states live (relative to the frontend dir). */
export const AUTH_DIR = "playwright/.auth";
export const SHOPPER_STATE = `${AUTH_DIR}/shopper.json`;
export const STAFF_STATE = `${AUTH_DIR}/staff.json`;

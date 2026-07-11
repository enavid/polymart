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
    description: "A balanced, everyday medium roast with notes of cocoa and citrus.",
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

/** A valid address the address-book spec can save without editing anything. */
export const ADDRESS = {
  recipientName: "Sara Ahmadi",
  phoneNumber: "09123456789",
  province: "Tehran",
  city: "Tehran",
  postalCode: "1234567890",
  line1: "Valiasr St, No. 1",
};

export const ADDRESS_LIMIT = 20;

/**
 * The shopper's persistent default shipping address, seeded by `seed_e2e`. Checkout
 * ships to it; the address-book spec is written to preserve it (it never deletes this
 * recipient), so the checkout and address-book specs can share the one seeded shopper
 * without racing on a shared, deleted address. Mirrors
 * `SHOPPER_ADDRESS_*` in the backend seed command.
 */
export const SHOPPER_ADDRESS = {
  recipientName: "خانهٔ شاپر",
  city: "تهران",
};

/** A variant that is priced only in another channel, so it is unavailable here. */
export const UNAVAILABLE_VARIANT = { sku: "HB-1000", productCode: "house-blend" };

export const PRODUCT_TYPE_CODE = "coffee";
// `child`/`root` are the slugs shown in the categories table; `childName` is the
// display name the products manager uses as its category-group accordion header.
export const CATEGORY = { root: "hot-drinks", child: "coffee-beans", childName: "Coffee Beans" };
export const COLLECTION = "featured";

/** Where the saved auth storage states live (relative to the frontend dir). */
export const AUTH_DIR = "playwright/.auth";
export const SHOPPER_STATE = `${AUTH_DIR}/shopper.json`;
export const STAFF_STATE = `${AUTH_DIR}/staff.json`;

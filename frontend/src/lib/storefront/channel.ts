/**
 * The storefront's active channel.
 *
 * A cart and its prices are per-channel (see the catalog per-channel pricing and
 * the cart context). Until multi-channel channel-switching lands, the storefront
 * runs against a single channel: its slug comes from an env var so a deployment can
 * point at whichever channel it sells, with a sensible default for local dev.
 */

export const STOREFRONT_CHANNEL =
  process.env.NEXT_PUBLIC_STOREFRONT_CHANNEL ?? "ir-main";

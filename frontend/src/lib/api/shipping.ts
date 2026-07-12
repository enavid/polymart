/**
 * Typed shipping API module (Phase 5, flat-rate slice).
 *
 * Mirrors the backend `GET /shipping/methods/` endpoint. Methods are public channel
 * configuration (no auth), so the storefront can list them at checkout for the shopper to
 * pick one. The price is a string end-to-end -- the exact Decimal the backend holds -- and
 * is never parsed into a float; the shipping cost captured on the order is the server's.
 */

import { apiGet, toQuery } from "@/lib/api/client";

/** One delivery method a channel offers, with its flat price and estimated window. */
export interface ShippingMethod {
  code: string;
  name: string;
  /** Exact string amount (flat rate). */
  price: string;
  currency: string;
  min_days: number;
  max_days: number;
  /** True for a pickup (BOPIS) method: an order using it captures no shipping address. */
  is_pickup: boolean;
}

interface ShippingMethodsResponse {
  channel: string;
  methods: ShippingMethod[];
}

/** A shipping destination; its province selects the zoned rate for each method. */
export interface ShippingDestination {
  province?: string;
  city?: string;
}

/**
 * List the shipping methods a channel offers (public; empty if none configured).
 *
 * When a `destination` province is given, each method's price is resolved for the zone it
 * falls into (falling back to the default rate); without one, the default rates are listed.
 * The price stays the server's exact string either way -- the checkout captures whatever the
 * backend re-resolves from the order's address, so this is only what to display.
 */
export async function listShippingMethods(
  channel: string,
  destination?: ShippingDestination,
): Promise<ShippingMethod[]> {
  const query: Record<string, string> = { channel };
  if (destination?.province) query.province = destination.province;
  if (destination?.city) query.city = destination.city;
  const response = await apiGet<ShippingMethodsResponse>(`/shipping/methods/${toQuery(query)}`);
  return response.methods;
}

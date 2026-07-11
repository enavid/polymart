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
}

interface ShippingMethodsResponse {
  channel: string;
  methods: ShippingMethod[];
}

/** List the shipping methods a channel offers (public; empty if none configured). */
export async function listShippingMethods(channel: string): Promise<ShippingMethod[]> {
  const response = await apiGet<ShippingMethodsResponse>(
    `/shipping/methods/${toQuery({ channel })}`,
  );
  return response.methods;
}

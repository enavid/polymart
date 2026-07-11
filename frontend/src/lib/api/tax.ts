/**
 * Typed tax API module (Phase 5, tax slice).
 *
 * Mirrors the backend `GET /tax/rate/` endpoint. The tax rate is public channel configuration
 * (no auth), so the storefront can show "prices include X% VAT" and preview the tax on the
 * checkout total. The rate is a string end-to-end -- the exact Decimal the backend holds -- and
 * `null` for a channel that levies no tax. The tax captured on a placed order is the server's.
 */

import { apiGet, toQuery } from "@/lib/api/client";

interface TaxRateResponse {
  channel: string;
  /** Percentage rate as an exact string (e.g. "9"), or null when the channel is untaxed. */
  rate: string | null;
}

/**
 * Read the tax rate a channel levies (public; `null` when the channel is not taxed).
 *
 * Used to preview the tax on the checkout total before the order exists server-side; the
 * authoritative tax is captured on the placed order.
 */
export async function getTaxRate(channel: string): Promise<string | null> {
  const response = await apiGet<TaxRateResponse>(`/tax/rate/${toQuery({ channel })}`);
  return response.rate;
}

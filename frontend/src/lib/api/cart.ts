/**
 * Typed cart API module (Phase 3).
 *
 * Mirrors the backend cart endpoints one-to-one so UI components never touch raw
 * fetch or response shapes. The cart is always resolved from the authenticated user
 * (cookie-JWT, credentials:'include'); there is no cart id in the URL space, so a
 * shopper can only ever reach their own cart. Money is a string end-to-end -- the
 * exact Decimal the backend computed -- and is never parsed into a float.
 */

import { apiDelete, apiGet, apiPost, apiPut, toQuery } from "@/lib/api/client";

/** One priced cart line. Prices are `null` when the line is unavailable. */
export interface CartLine {
  sku: string;
  quantity: number;
  /** Exact string amount, or null when the variant has no price in the channel. */
  unit_price: string | null;
  line_total: string | null;
  available: boolean;
}

/** A cart projected with current prices: its lines plus the summed total. */
export interface Cart {
  channel: string;
  currency: string;
  items: CartLine[];
  /** Exact string total, summing only the available lines. */
  total: string;
}

export interface AddCartItemInput {
  channel: string;
  sku: string;
  quantity: number;
}

export function getCart(channel: string): Promise<Cart> {
  return apiGet<Cart>(`/cart/${toQuery({ channel })}`);
}

export function addCartItem(input: AddCartItemInput): Promise<Cart> {
  return apiPost<Cart>("/cart/items/", input);
}

export function updateCartItem(
  sku: string,
  channel: string,
  quantity: number,
): Promise<Cart> {
  return apiPut<Cart>(`/cart/items/${sku}/`, { channel, quantity });
}

export function removeCartItem(sku: string, channel: string): Promise<Cart> {
  return apiDelete<Cart>(`/cart/items/${sku}/${toQuery({ channel })}`);
}

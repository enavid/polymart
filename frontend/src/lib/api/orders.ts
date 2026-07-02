/**
 * Typed order API module (Phase 3, checkout slice).
 *
 * Mirrors the backend order endpoints one-to-one so UI components never touch raw
 * fetch or response shapes. Every route resolves the order from the authenticated user
 * (cookie-JWT, credentials:'include'); there is no owner id in the request, and the
 * order number is opaque, so a shopper can only ever reach their own orders. Money is a
 * string end-to-end -- the exact Decimal the backend captured -- and is never parsed
 * into a float.
 */

import { apiGet, apiPost, toQuery } from "@/lib/api/client";

/** The order lifecycle states, matching the backend state machine. */
export type OrderStatus = "pending" | "paid" | "fulfilled" | "cancelled";

/** One captured order line (prices are the snapshot taken at placement). */
export interface OrderLine {
  sku: string;
  quantity: number;
  /** Exact string amounts captured at placement time. */
  unit_price: string;
  line_total: string;
}

/** A placed order. */
export interface Order {
  number: string;
  channel: string;
  currency: string;
  status: OrderStatus;
  /** Exact string total. */
  total: string;
  placed_at: string;
  items: OrderLine[];
}

/** One page of a shopper's orders. */
export interface OrderPage {
  count: number;
  limit: number;
  offset: number;
  results: Order[];
}

/** Place an order by checking out the given channel's cart. */
export function placeOrder(channel: string): Promise<Order> {
  return apiPost<Order>("/orders/", { channel });
}

/** List the authenticated shopper's own orders (newest first). */
export function listMyOrders(params: { limit?: number; offset?: number } = {}): Promise<OrderPage> {
  return apiGet<OrderPage>(`/orders/${toQuery(params)}`);
}

/** Read one of the authenticated shopper's orders by number. */
export function getMyOrder(number: string): Promise<Order> {
  return apiGet<Order>(`/orders/${number}/`);
}

/** Cancel one of the authenticated shopper's still-pending orders. */
export function cancelOrder(number: string): Promise<Order> {
  return apiPost<Order>(`/orders/${number}/cancel/`);
}

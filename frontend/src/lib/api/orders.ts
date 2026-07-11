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

import type { AddressInput } from "@/lib/api/addresses";
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

/** The shipping address captured on an order (a snapshot taken at placement). */
export interface OrderShippingAddress {
  recipient_name: string;
  phone_number: string;
  province: string;
  city: string;
  postal_code: string;
  line1: string;
  line2: string | null;
}

/** A placed order. */
export interface Order {
  number: string;
  channel: string;
  currency: string;
  status: OrderStatus;
  /** Exact string amounts. `total` is the grand total = `subtotal` + `shipping_cost` + `tax`. */
  subtotal: string;
  shipping_cost: string;
  /** The captured shipping method, or null for an order with no delivery charge. */
  shipping_method: string | null;
  shipping_method_name: string | null;
  /** The captured tax amount and percentage rate, or null for an order in an untaxed channel. */
  tax: string | null;
  tax_rate: string | null;
  total: string;
  placed_at: string;
  items: OrderLine[];
  shipping_address: OrderShippingAddress;
}

/** One page of a shopper's orders. */
export interface OrderPage {
  count: number;
  limit: number;
  offset: number;
  results: Order[];
}

/**
 * How the order's shipping address is supplied: a signed-in shopper picks one of their
 * saved addresses by id; a guest (no address book) enters a one-off address inline. The
 * order captures a snapshot either way -- exactly one of the two is sent.
 */
export type PlaceOrderShipping =
  | { addressId: string }
  | { shippingAddress: AddressInput };

/**
 * Place an order by checking out the given channel's cart, shipping to either a saved
 * address (`{ addressId }`) or a one-off inline address (`{ shippingAddress }`), by the
 * chosen `shippingMethod` (its cost is quoted server-side and captured onto the order).
 */
export function placeOrder(
  channel: string,
  shipping: PlaceOrderShipping,
  shippingMethod: string,
): Promise<Order> {
  const base =
    "addressId" in shipping
      ? { channel, address_id: shipping.addressId }
      : { channel, shipping_address: shipping.shippingAddress };
  return apiPost<Order>("/orders/", { ...base, shipping_method: shippingMethod });
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

/** One line of a manual order: a variant SKU and a positive quantity. */
export interface ManualOrderItem {
  sku: string;
  quantity: number;
}

/** Fields staff supply to create a manual order (a pre-invoice). */
export interface ManualOrderInput {
  channel: string;
  items: ManualOrderItem[];
  shipping_address: AddressInput;
}

/**
 * A pre-invoice (proforma): the full order (which carries `tax`/`tax_rate`) plus a document
 * marker and a `grand_total` equal to the order total (which already includes the tax).
 */
export interface PreInvoice extends Order {
  document_type: "pre_invoice";
  grand_total: string;
}

/**
 * Create a manual order (a pre-invoice) from staff-supplied lines. Requires the
 * `manage_orders` permission on the backend; a shopper's own checkout uses `placeOrder`.
 */
export function createManualOrder(input: ManualOrderInput): Promise<Order> {
  return apiPost<Order>("/orders/manual/", input);
}

/** Read any order's pre-invoice by number (staff only, `manage_orders`). */
export function getPreInvoice(number: string): Promise<PreInvoice> {
  return apiGet<PreInvoice>(`/orders/${number}/pre-invoice/`);
}

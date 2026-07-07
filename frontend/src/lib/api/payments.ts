/**
 * Typed payment API module (Phase 4, payments-foundation + COD slice).
 *
 * Mirrors the backend payment endpoints one-to-one so UI components never touch raw fetch
 * or response shapes. Every route resolves the payment from the request's owner (a
 * signed-in user's cookie-JWT, or a guest's HttpOnly session cookie, credentials:'include');
 * there is no owner id in the request, and the references are opaque, so a shopper can only
 * ever reach their own payments. The amount is a string end-to-end -- the exact Decimal the
 * backend captured from the order total -- and is never parsed into a float.
 */

import { apiGet, apiPost } from "@/lib/api/client";

/** How a shopper pays. COD, online, and wallet are live; card-to-card arrives later. */
export type PaymentMethod = "cod" | "card_to_card" | "online" | "wallet";

/** The payment lifecycle states, matching the backend state machine. */
export type PaymentStatus =
  | "pending"
  | "authorized"
  | "captured"
  | "failed"
  | "cancelled"
  | "voided"
  | "refunded";

/** What the shopper must do next after initiating a payment. */
export type PaymentNextAction = "none" | "redirect";

/** A payment against one order. */
export interface Payment {
  reference: string;
  order_number: string;
  method: PaymentMethod;
  /** Exact string amount captured from the order total. */
  amount: string;
  currency: string;
  status: PaymentStatus;
  created_at: string;
  /**
   * The buyer's submitted card-to-card transfer reference, or null for every other method
   * and until a card-to-card buyer submits it.
   */
  transfer_reference: string | null;
}

/** The merchant's receiving card a buyer transfers to for a card-to-card payment. */
export interface CardToCardInstructions {
  card_number: string;
  card_holder: string;
}

/**
 * The result of initiating a payment: the payment plus what to do next. For COD,
 * `next_action` is `"none"` and `redirect_url` is null (nothing more to do -- pay on
 * delivery); an online gateway would return `"redirect"` with a `redirect_url`.
 */
export interface PaymentInitiation extends Payment {
  next_action: PaymentNextAction;
  redirect_url: string | null;
}

/** Initiate a payment for one of the shopper's own orders by the chosen method. */
export function initiatePayment(
  orderNumber: string,
  method: PaymentMethod,
): Promise<PaymentInitiation> {
  return apiPost<PaymentInitiation>("/payments/", {
    order_number: orderNumber,
    method,
  });
}

/** Read the payment for one of the shopper's own orders (404 if none was initiated). */
export function getPaymentForOrder(orderNumber: string): Promise<Payment> {
  return apiGet<Payment>(`/payments/for-order/${orderNumber}/`);
}

/** Read one of the shopper's payments by reference. */
export function getPayment(reference: string): Promise<Payment> {
  return apiGet<Payment>(`/payments/${reference}/`);
}

/**
 * Read the destination card a buyer must transfer to for their own card-to-card order
 * (owner-scoped; another shopper's order is a 404). The channel's receiving card is
 * server-owned config -- never entered by the buyer.
 */
export function getCardToCardInstructions(
  orderNumber: string,
): Promise<CardToCardInstructions> {
  return apiGet<CardToCardInstructions>(`/payments/for-order/${orderNumber}/card-to-card/`);
}

/** Submit the buyer's card-to-card transfer reference for their own pending order. */
export function submitTransferReference(
  orderNumber: string,
  transferReference: string,
): Promise<Payment> {
  return apiPost<Payment>(`/payments/for-order/${orderNumber}/transfer-reference/`, {
    transfer_reference: transferReference,
  });
}

/** Staff: confirm a card-to-card transfer, capturing the payment (manage_orders). */
export function confirmCardToCardPayment(reference: string): Promise<Payment> {
  return apiPost<Payment>(`/payments/${reference}/confirm/`, {});
}

/** Staff: reject a card-to-card transfer, failing the payment (manage_orders). */
export function rejectCardToCardPayment(reference: string): Promise<Payment> {
  return apiPost<Payment>(`/payments/${reference}/reject/`, {});
}

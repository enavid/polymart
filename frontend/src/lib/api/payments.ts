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

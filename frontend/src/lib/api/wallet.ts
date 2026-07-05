/**
 * Typed wallet API module (Phase 4, internal-wallet + refund-to-wallet slice).
 *
 * Mirrors the backend wallet + refund endpoints one-to-one so UI components never touch raw
 * fetch or response shapes. The wallet is authenticated-only and owner-scoped: the balance
 * and statement are resolved from the signed-in user's cookie-JWT (credentials:'include'),
 * never from an id in the request, so a user only ever reads their own wallet. Refunding a
 * captured payment to the shopper's wallet is a staff action addressed by the payment's
 * opaque reference. Every amount is a string end-to-end -- the exact Decimal the backend
 * stored -- and is never parsed into a float except for display.
 */

import { apiGet, apiPost } from "@/lib/api/client";
import type { Payment } from "@/lib/api/payments";

/** The direction of a wallet ledger entry. */
export type WalletTransactionType = "credit" | "debit";

/** One append-only wallet ledger entry (a single movement of value). */
export interface WalletTransaction {
  type: WalletTransactionType;
  /** Exact string amount of this movement. */
  amount: string;
  currency: string;
  reason: string;
  /** The balance once this movement was applied (exact string). */
  balance_after: string;
  /** What caused the movement (a payment reference for a refund), or null. */
  source_reference: string | null;
  created_at: string;
}

/** A user's internal store-credit balance plus their recent statement. */
export interface Wallet {
  /** Exact string balance (the source of truth; never recomputed client-side). */
  balance: string;
  currency: string;
  transactions: WalletTransaction[];
}

/** Read the authenticated user's own wallet: balance and recent ledger entries. */
export function getWallet(): Promise<Wallet> {
  return apiGet<Wallet>("/wallet/");
}

/**
 * Refund a captured payment to the shopper's wallet (staff only, by payment reference).
 *
 * Returns the payment in its new `refunded` state. Idempotent server-side: refunding an
 * already-refunded payment returns it unchanged without crediting again.
 */
export function refundPaymentToWallet(reference: string): Promise<Payment> {
  return apiPost<Payment>(`/payments/${reference}/refund/`, {});
}

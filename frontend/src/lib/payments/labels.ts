/**
 * Maps a payment method and status to their i18n message keys (in the `payment` namespace).
 *
 * Kept in one place so the storefront renders the backend's strings through localized
 * labels rather than showing raw enum values, and so both mappings are exhaustive over the
 * `PaymentMethod` / `PaymentStatus` unions at compile time.
 */

import type { PaymentMethod, PaymentStatus } from "@/lib/api/payments";

const METHOD_KEYS: Record<PaymentMethod, string> = {
  cod: "methodCod",
  card_to_card: "methodCardToCard",
  online: "methodOnline",
  wallet: "methodWallet",
};

const STATUS_KEYS: Record<PaymentStatus, string> = {
  pending: "statusPending",
  authorized: "statusAuthorized",
  captured: "statusCaptured",
  failed: "statusFailed",
  cancelled: "statusCancelled",
  voided: "statusVoided",
  refunded: "statusRefunded",
};

export function paymentMethodKey(method: PaymentMethod): string {
  return METHOD_KEYS[method];
}

export function paymentStatusKey(status: PaymentStatus): string {
  return STATUS_KEYS[status];
}

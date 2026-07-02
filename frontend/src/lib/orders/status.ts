/**
 * Maps an order status to its i18n message key (in the `orders` namespace).
 *
 * Kept in one place so the storefront renders the backend's status string through a
 * localized label rather than showing the raw enum value, and so the mapping is
 * exhaustive over the `OrderStatus` union at compile time.
 */

import type { OrderStatus } from "@/lib/api/orders";

const STATUS_KEYS: Record<OrderStatus, string> = {
  pending: "statusPending",
  paid: "statusPaid",
  fulfilled: "statusFulfilled",
  cancelled: "statusCancelled",
};

export function orderStatusKey(status: OrderStatus): string {
  return STATUS_KEYS[status];
}

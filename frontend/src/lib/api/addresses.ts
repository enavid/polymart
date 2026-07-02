/**
 * Typed address-book API module (Phase 3, address-book slice).
 *
 * Mirrors the backend address endpoints one-to-one so UI components never touch raw
 * fetch or response shapes. Every route resolves addresses from the authenticated user
 * (cookie-JWT, credentials:'include'); there is no owner id in the request, and the
 * address id is opaque, so a shopper can only ever reach their own addresses.
 */

import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api/client";

/** A saved shipping address in the shopper's address book. */
export interface Address {
  id: string;
  recipient_name: string;
  phone_number: string;
  province: string;
  city: string;
  postal_code: string;
  line1: string;
  line2: string | null;
  is_default: boolean;
  created_at: string;
}

/** Fields the shopper supplies when saving or editing an address. */
export interface AddressInput {
  recipient_name: string;
  phone_number: string;
  province: string;
  city: string;
  postal_code: string;
  line1: string;
  line2?: string;
}

/** List the authenticated shopper's own address book (default first). */
export function listMyAddresses(): Promise<Address[]> {
  return apiGet<Address[]>("/addresses/");
}

/**
 * Save a new address. The shopper's first address always becomes their default;
 * marking a later one default is a separate action (`setDefaultAddress`).
 */
export function createAddress(input: AddressInput): Promise<Address> {
  return apiPost<Address>("/addresses/", input);
}

/** Edit an existing address's contact/location details (never its default status). */
export function updateAddress(id: string, input: AddressInput): Promise<Address> {
  return apiPut<Address>(`/addresses/${id}/`, input);
}

/** Remove an address from the shopper's address book. */
export function deleteAddress(id: string): Promise<void> {
  return apiDelete<void>(`/addresses/${id}/`);
}

/** Mark an address as the shopper's sole default. */
export function setDefaultAddress(id: string): Promise<Address> {
  return apiPost<Address>(`/addresses/${id}/default/`);
}

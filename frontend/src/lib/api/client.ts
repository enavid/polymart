/**
 * Typed API client wrapper.
 *
 * All backend calls go through this module so UI components never touch raw
 * fetch or backend response shapes directly. This is the provider-swap seam
 * (see docs/02-features-report.md) that keeps the storefront decoupled from the
 * Django REST API.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

/**
 * Typed API client wrapper.
 *
 * All backend calls go through this module so UI components never touch raw
 * fetch or backend response shapes directly. This is the provider-swap seam
 * (see docs/02-features-report.md) that keeps the storefront decoupled from the
 * Django REST API.
 *
 * Auth: the backend issues JWTs in HttpOnly cookies (see
 * docs/adr/0005-phone-first-identity-and-cookie-jwt-auth.md). The browser sends
 * them automatically as long as every request opts in with credentials:'include'.
 * SameSite=Lax cookies mean no separate CSRF token is required.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

/** A failed API call. `detail` carries the backend's human-readable message. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

interface ErrorBody {
  detail?: unknown;
}

async function readDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ErrorBody;
    if (typeof body.detail === "string" && body.detail.length > 0) {
      return body.detail;
    }
  } catch {
    // Non-JSON or empty error body: fall through to the status-based message.
  }
  return `request failed with status ${response.status}`;
}

async function parseBody<T>(response: Response): Promise<T> {
  // 204, or a 200 with an empty body (e.g. refresh/logout/grants), has nothing
  // to parse. Callers type these as `void`.
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  if (text.length === 0) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
): Promise<T> {
  const hasBody = body !== undefined;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      Accept: "application/json",
      ...(hasBody ? { "Content-Type": "application/json" } : {}),
    },
    credentials: "include",
    cache: "no-store",
    body: hasBody ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }
  return parseBody<T>(response);
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>("GET", path);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>("POST", path, body ?? {});
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return request<T>("PUT", path, body ?? {});
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return request<T>("PATCH", path, body ?? {});
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>("DELETE", path);
}

/** Build a query string from defined params (skips undefined/empty values). */
export function toQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query.length > 0 ? `?${query}` : "";
}

/**
 * A readable, non-sensitive hint that a session probably exists.
 *
 * The auth token lives in an HttpOnly cookie that JavaScript cannot read, so the
 * client has no other way to know whether it is worth calling `/auth/me/`. Without
 * this, every guest page would fire a probe that 401s and logs a "Failed to load
 * resource" error to the browser console. We set the hint on login/register and
 * clear it on logout (and self-heal by clearing it if a probe unexpectedly 401s),
 * so a never-signed-in visitor never probes. The hint carries no identity — it is
 * only a boolean "try the session endpoint".
 */

const KEY = "pm_signed_in";

export function markSignedIn(): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(KEY, "1");
  }
}

export function clearSignedIn(): void {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(KEY);
  }
}

export function hasSignedInHint(): boolean {
  return typeof window !== "undefined" && window.localStorage.getItem(KEY) === "1";
}

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
// A same-tab change to the hint (login/logout in this tab) does not fire the `storage`
// event -- that only fires in *other* tabs -- so we dispatch our own event to notify
// same-tab subscribers (see `subscribeSignedInHint`).
const EVENT = "pm-session-hint";

function notifyHintChanged(): void {
  window.dispatchEvent(new Event(EVENT));
}

export function markSignedIn(): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(KEY, "1");
    notifyHintChanged();
  }
}

export function clearSignedIn(): void {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(KEY);
    notifyHintChanged();
  }
}

export function hasSignedInHint(): boolean {
  return typeof window !== "undefined" && window.localStorage.getItem(KEY) === "1";
}

/**
 * Subscribe to hint changes for `useSyncExternalStore`. Listens same-tab (our custom
 * event, dispatched by mark/clear) and cross-tab (the browser `storage` event), so a
 * component reading the hint re-renders when a sign-in/out happens anywhere.
 */
export function subscribeSignedInHint(onChange: () => void): () => void {
  if (typeof window === "undefined") {
    return () => {};
  }
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

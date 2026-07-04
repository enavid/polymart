import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clearSignedIn,
  hasSignedInHint,
  markSignedIn,
  subscribeSignedInHint,
} from "@/lib/auth/session-hint";

afterEach(() => window.localStorage.clear());

describe("session hint", () => {
  it("is absent for a fresh visitor", () => {
    expect(hasSignedInHint()).toBe(false);
  });

  it("is present after marking signed in", () => {
    markSignedIn();
    expect(hasSignedInHint()).toBe(true);
  });

  it("is absent again after clearing", () => {
    markSignedIn();
    clearSignedIn();
    expect(hasSignedInHint()).toBe(false);
  });

  it("notifies same-tab subscribers when the hint changes", () => {
    // `useSyncExternalStore` relies on this so an auth-gated page re-renders the moment
    // the visitor signs in or out in this tab (the `storage` event only fires cross-tab).
    const onChange = vi.fn();
    const unsubscribe = subscribeSignedInHint(onChange);

    markSignedIn();
    clearSignedIn();

    expect(onChange).toHaveBeenCalledTimes(2);

    unsubscribe();
    markSignedIn();
    expect(onChange).toHaveBeenCalledTimes(2); // no longer notified after unsubscribe
  });
});

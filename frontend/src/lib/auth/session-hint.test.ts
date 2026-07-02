import { afterEach, describe, expect, it } from "vitest";

import { clearSignedIn, hasSignedInHint, markSignedIn } from "@/lib/auth/session-hint";

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
});

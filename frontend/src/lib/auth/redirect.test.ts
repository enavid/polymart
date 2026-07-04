import { describe, expect, it } from "vitest";

import { resolveRedirect } from "@/lib/auth/redirect";

describe("resolveRedirect", () => {
  it("returns home when there is no next value", () => {
    expect(resolveRedirect(null)).toBe("/");
    expect(resolveRedirect(undefined)).toBe("/");
    expect(resolveRedirect("")).toBe("/");
  });

  it("honours a same-origin absolute path", () => {
    expect(resolveRedirect("/cart")).toBe("/cart");
    expect(resolveRedirect("/orders/ORD-1")).toBe("/orders/ORD-1");
  });

  it("rejects off-site and non-absolute targets (open-redirect guard)", () => {
    expect(resolveRedirect("//evil.example.com")).toBe("/");
    expect(resolveRedirect("/\\evil.example.com")).toBe("/");
    expect(resolveRedirect("https://evil.example.com")).toBe("/");
    expect(resolveRedirect("javascript:alert(1)")).toBe("/");
    expect(resolveRedirect("cart")).toBe("/");
  });
});

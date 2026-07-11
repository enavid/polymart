import { describe, expect, it } from "vitest";

import { sumMoneyStrings } from "@/lib/format";

describe("sumMoneyStrings", () => {
  it("adds two whole amounts exactly at 4-dp precision", () => {
    expect(sumMoneyStrings("240000.0000", "50000.0000")).toBe("290000.0000");
  });

  it("adds amounts that arrive without a fraction", () => {
    expect(sumMoneyStrings("240000", "50000")).toBe("290000.0000");
  });

  it("adds fractional amounts without float drift", () => {
    // 0.1 + 0.2 is the classic float trap; scaled-integer arithmetic keeps it exact.
    expect(sumMoneyStrings("0.1000", "0.2000")).toBe("0.3000");
  });

  it("carries across the decimal boundary", () => {
    expect(sumMoneyStrings("1.7500", "0.2500")).toBe("2.0000");
  });

  it("treats a single argument as itself (normalised to 4 dp)", () => {
    expect(sumMoneyStrings("120000")).toBe("120000.0000");
  });

  it("sums more than two amounts", () => {
    expect(sumMoneyStrings("100.0000", "50.0000", "0.5000")).toBe("150.5000");
  });
});

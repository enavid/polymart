import { describe, expect, it } from "vitest";

import { formatPercent, sumMoneyStrings, taxAmountString } from "@/lib/format";

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

describe("taxAmountString", () => {
  it("computes a whole-percentage tax exactly (matches the backend)", () => {
    // 170000 * 9% = 15300 (goods 120000 + shipping 50000 in the checkout preview).
    expect(taxAmountString("170000.0000", "9")).toBe("15300.0000");
  });

  it("computes tax on the goods subtotal alone", () => {
    expect(taxAmountString("240000.0000", "9")).toBe("21600.0000");
  });

  it("rounds half-up at the stored precision, like the backend service", () => {
    // 1.2346 * 10% = 0.12346 -> half-up to 4 dp = 0.1235.
    expect(taxAmountString("1.2346", "10")).toBe("0.1235");
  });

  it("computes an exact non-rounding fractional result", () => {
    // 33333 * 9% = 2999.97 exactly.
    expect(taxAmountString("33333.0000", "9")).toBe("2999.9700");
  });

  it("handles a fractional rate", () => {
    // 100000 * 9.5% = 9500.
    expect(taxAmountString("100000.0000", "9.5")).toBe("9500.0000");
  });

  it("is zero for a zero base", () => {
    expect(taxAmountString("0.0000", "9")).toBe("0.0000");
  });
});

describe("formatPercent", () => {
  it("drops trailing zeros from a stored rate", () => {
    // "9.0000" (the exact stored form) displays as «۹».
    expect(formatPercent("9.0000")).toBe("۹");
  });

  it("keeps a genuine fractional rate", () => {
    expect(formatPercent("9.5000")).toBe("۹٫۵");
  });
});

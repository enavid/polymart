// Persian-first formatting helpers. The Jalali calendar and Persian digits are a
// first-class requirement for the Iranian market (see CLAUDE.md).

const JALALI_LOCALE = "fa-IR-u-ca-persian";

/** Format an ISO-8601 timestamp as a Jalali date-time with Persian digits. */
export function formatJalaliDateTime(iso: string): string {
  return new Intl.DateTimeFormat(JALALI_LOCALE, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

/**
 * Format an amount in its ISO-4217 currency, localized for Iran.
 *
 * Iranian retail quotes prices in Toman, while the ledger currency is the Rial
 * (IRR, the only ISO code for Iran; 1 Toman = 10 Rial). So we present IRR amounts
 * in Toman -- divide by ten and label «تومان» -- which is what shoppers expect,
 * and format every other currency with the standard Intl currency style. This is
 * display-only: the server's exact amount stays the source of truth.
 */
export function formatCurrency(amount: number, currency: string): string {
  if (currency === "IRR") {
    const toman = new Intl.NumberFormat("fa-IR").format(Math.round(amount / 10));
    return `${toman} تومان`;
  }
  return new Intl.NumberFormat("fa-IR", {
    style: "currency",
    currency,
  }).format(amount);
}

/**
 * Format a money amount that arrived as an exact string (the backend's Decimal).
 *
 * The conversion to a number is for *display only*: the source of truth is the
 * server string, and the UI never recomputes line totals or the cart total -- it
 * only renders what the backend already computed. A blank/`null` amount (an
 * unavailable line) renders as an em dash.
 */
export function formatMoneyString(amount: string | null, currency: string): string {
  if (amount === null || amount === "") {
    return "—";
  }
  return formatCurrency(Number(amount), currency);
}

// A tax rate carries at most four decimal places (the domain bound); display drops any
// trailing zeros within that precision.
const RATE_MAX_FRACTION_DIGITS = 4;

/**
 * Format a percentage rate (an exact string such as "9" or "9.5000") for display.
 *
 * The rate is a label, not money: it is parsed to a number and localised with Persian
 * digits, dropping trailing zeros (so "9.0000" shows as «۹»). The money amounts on screen
 * remain the server's exact strings; only this display label is derived.
 */
export function formatPercent(rate: string): string {
  return new Intl.NumberFormat("fa-IR", {
    maximumFractionDigits: RATE_MAX_FRACTION_DIGITS,
  }).format(Number(rate));
}

// The backend stores money at four decimal places; scale to integer "milli-units" so
// addition is exact (no binary-float drift) for the one place the UI must combine two
// server amounts: the checkout preview total (goods subtotal + shipping cost) shown before
// the order exists server-side. The authoritative grand total is still the placed order's.
const MONEY_SCALE = 4;

function toScaledInt(amount: string): bigint {
  const negative = amount.startsWith("-");
  const [whole, fraction = ""] = amount.replace("-", "").split(".");
  const padded = (fraction + "0".repeat(MONEY_SCALE)).slice(0, MONEY_SCALE);
  const scaled = BigInt(whole || "0") * 10n ** BigInt(MONEY_SCALE) + BigInt(padded || "0");
  return negative ? -scaled : scaled;
}

/**
 * Add exact decimal money strings, returning a string at the stored 4-dp precision.
 *
 * Uses integer (BigInt) arithmetic on scaled amounts so no float rounding is introduced --
 * the same discipline the backend uses. Only for previewing a total the shopper has not yet
 * committed (the order the server places is the source of truth once it exists).
 */
export function sumMoneyStrings(...amounts: string[]): string {
  const total = amounts.reduce((acc, amount) => acc + toScaledInt(amount), 0n);
  return scaledToMoneyString(total);
}

function scaledToMoneyString(scaled: bigint): string {
  const negative = scaled < 0n;
  const digits = (negative ? -scaled : scaled).toString().padStart(MONEY_SCALE + 1, "0");
  const whole = digits.slice(0, -MONEY_SCALE);
  const fraction = digits.slice(-MONEY_SCALE);
  return `${negative ? "-" : ""}${whole}.${fraction}`;
}

/**
 * Preview the tax due on a taxable money string at a percentage rate, matching the backend.
 *
 * Uses the *same* exact integer arithmetic and half-up rounding as the server's tax domain
 * service, so the previewed tax cannot drift from the amount the backend captures. This is
 * only for the pre-placement preview (the tax on a placed order is the server's value). Both
 * inputs are exact strings (never binary floats); a non-negative money amount is assumed
 * (money is non-negative), so half-up is `floor((n + d/2) / d)`.
 */
export function taxAmountString(taxableBase: string, ratePercent: string): string {
  const baseUnits = toScaledInt(taxableBase); // base * 10^MONEY_SCALE
  const rateUnits = toScaledInt(ratePercent); // rate * 10^MONEY_SCALE
  // tax * 10^SCALE = base * rate / 100 * 10^SCALE = baseUnits * rateUnits / (10^SCALE * 100).
  const denominator = 10n ** BigInt(MONEY_SCALE) * 100n;
  const numerator = baseUnits * rateUnits;
  const scaledTax = (numerator + denominator / 2n) / denominator; // half-up (non-negative)
  return scaledToMoneyString(scaledTax);
}

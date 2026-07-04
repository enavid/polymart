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

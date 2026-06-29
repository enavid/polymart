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

/** Format an amount in its ISO-4217 currency, localized for Iran. */
export function formatCurrency(amount: number, currency: string): string {
  return new Intl.NumberFormat("fa-IR", {
    style: "currency",
    currency,
  }).format(amount);
}

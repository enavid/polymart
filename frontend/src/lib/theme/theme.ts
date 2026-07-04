/**
 * Theme primitives shared by the no-flash boot script and the React toggle.
 *
 * The design system exposes light and dark palettes as CSS custom properties in
 * `globals.css`; which one is active is decided purely by a `light`/`dark` class
 * on <html>. This module owns the small, framework-free logic that reads the
 * user's saved choice, resolves "system" against the OS preference, and applies
 * the resolved palette to the document. Keeping it framework-free lets the exact
 * same logic run inside the inline boot script (as a string) with no drift.
 */

export type ThemeChoice = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

/** localStorage key holding the user's explicit choice (absent ⇒ follow system). */
export const THEME_STORAGE_KEY = "pm-theme";

const CHOICES: readonly ThemeChoice[] = ["light", "dark", "system"];

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return typeof value === "string" && (CHOICES as readonly string[]).includes(value);
}

/** The saved choice, or "system" when nothing valid is stored (or storage is unavailable). */
export function readStoredChoice(): ThemeChoice {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    return isThemeChoice(raw) ? raw : "system";
  } catch {
    return "system";
  }
}

export function storeChoice(choice: ThemeChoice): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, choice);
  } catch {
    // Private-mode / disabled storage: the choice simply won't persist.
  }
}

/** Whether the OS currently prefers a dark color scheme. */
export function systemPrefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

/** Turn a choice into the concrete palette to paint, given the OS preference. */
export function resolveTheme(choice: ThemeChoice, prefersDark: boolean): ResolvedTheme {
  if (choice === "system") return prefersDark ? "dark" : "light";
  return choice;
}

/** Paint the resolved palette by toggling the html class + native color-scheme. */
export function applyResolvedTheme(resolved: ResolvedTheme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.classList.toggle("light", resolved === "light");
  root.style.colorScheme = resolved;
}

"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";

import {
  applyResolvedTheme,
  readStoredChoice,
  resolveTheme,
  storeChoice,
  systemPrefersDark,
  type ResolvedTheme,
  type ThemeChoice,
} from "./theme";

// Same-tab change signal. `storage` only fires in *other* tabs, so we emit our
// own event to re-render the toggle in the tab that made the change.
const THEME_EVENT = "pm-theme-change";

function subscribe(onChange: () => void): () => void {
  window.addEventListener(THEME_EVENT, onChange);
  window.addEventListener("storage", onChange);
  const mql = window.matchMedia("(prefers-color-scheme: dark)");
  // A system preference flip must re-render (and re-paint) while in "system" mode.
  mql.addEventListener("change", onChange);
  return () => {
    window.removeEventListener(THEME_EVENT, onChange);
    window.removeEventListener("storage", onChange);
    mql.removeEventListener("change", onChange);
  };
}

// The server can't know the stored choice; render "system" there and let the
// inline boot script (which already painted the correct palette pre-hydration)
// keep the DOM right. The toggle's label reconciles on the first client render.
const getServerChoice = (): ThemeChoice => "system";

const CYCLE: readonly ThemeChoice[] = ["system", "light", "dark"];

export interface ThemeController {
  choice: ThemeChoice;
  resolved: ResolvedTheme;
  setTheme: (choice: ThemeChoice) => void;
  cycleTheme: () => void;
}

/** Read + control the active theme. Re-renders on same-tab, cross-tab, and OS changes. */
export function useTheme(): ThemeController {
  const choice = useSyncExternalStore(subscribe, readStoredChoice, getServerChoice);
  const resolved = resolveTheme(choice, systemPrefersDark());

  // Keep the DOM in sync when the OS flips while in "system" mode (setTheme
  // handles explicit changes eagerly; this covers the passive case).
  useEffect(() => {
    applyResolvedTheme(resolved);
  }, [resolved]);

  const setTheme = useCallback((next: ThemeChoice) => {
    storeChoice(next);
    applyResolvedTheme(resolveTheme(next, systemPrefersDark()));
    window.dispatchEvent(new Event(THEME_EVENT));
  }, []);

  const cycleTheme = useCallback(() => {
    const current = readStoredChoice();
    const next = CYCLE[(CYCLE.indexOf(current) + 1) % CYCLE.length];
    storeChoice(next);
    applyResolvedTheme(resolveTheme(next, systemPrefersDark()));
    window.dispatchEvent(new Event(THEME_EVENT));
  }, []);

  return { choice, resolved, setTheme, cycleTheme };
}

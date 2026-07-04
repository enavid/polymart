import { afterEach, describe, expect, it, vi } from "vitest";

import {
  applyResolvedTheme,
  isThemeChoice,
  readStoredChoice,
  resolveTheme,
  storeChoice,
  systemPrefersDark,
  THEME_STORAGE_KEY,
} from "./theme";

afterEach(() => {
  localStorage.clear();
  document.documentElement.className = "";
  document.documentElement.style.colorScheme = "";
  vi.unstubAllGlobals();
});

describe("isThemeChoice", () => {
  it("accepts the three valid choices and rejects anything else", () => {
    expect(isThemeChoice("light")).toBe(true);
    expect(isThemeChoice("dark")).toBe(true);
    expect(isThemeChoice("system")).toBe(true);
    expect(isThemeChoice("sepia")).toBe(false);
    expect(isThemeChoice(null)).toBe(false);
    expect(isThemeChoice(undefined)).toBe(false);
  });
});

describe("readStoredChoice", () => {
  it("returns the stored choice when valid", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    expect(readStoredChoice()).toBe("dark");
  });

  it("falls back to 'system' when nothing is stored", () => {
    expect(readStoredChoice()).toBe("system");
  });

  it("falls back to 'system' when a garbage value is stored", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "neon");
    expect(readStoredChoice()).toBe("system");
  });
});

describe("storeChoice", () => {
  it("persists the choice so a later read returns it", () => {
    storeChoice("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(readStoredChoice()).toBe("light");
  });
});

describe("resolveTheme", () => {
  it("passes explicit light/dark through untouched", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("resolves 'system' from the OS preference", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });
});

describe("systemPrefersDark", () => {
  it("reflects the matchMedia result", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: true,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    expect(systemPrefersDark()).toBe(true);
  });
});

describe("applyResolvedTheme", () => {
  it("marks the document as dark and sets color-scheme", () => {
    applyResolvedTheme("dark");
    const root = document.documentElement;
    expect(root.classList.contains("dark")).toBe(true);
    expect(root.classList.contains("light")).toBe(false);
    expect(root.style.colorScheme).toBe("dark");
  });

  it("marks the document as light, clearing a previous dark class", () => {
    applyResolvedTheme("dark");
    applyResolvedTheme("light");
    const root = document.documentElement;
    expect(root.classList.contains("light")).toBe(true);
    expect(root.classList.contains("dark")).toBe(false);
    expect(root.style.colorScheme).toBe("light");
  });
});

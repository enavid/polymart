import "@testing-library/jest-dom/vitest";

// jsdom does not implement matchMedia, which the theme system queries for the
// OS light/dark preference. Provide a controllable stub defaulting to "light";
// individual tests override `window.matchMedia` when they need dark.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

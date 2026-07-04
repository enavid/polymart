import { afterEach, describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { ThemeToggle } from "@/components/layout/theme-toggle";
import messages from "@/i18n/messages/fa.json";
import { THEME_STORAGE_KEY } from "@/lib/theme/theme";
import { renderWithProviders } from "@/test/utils";

afterEach(() => {
  localStorage.clear();
  document.documentElement.className = "";
});

describe("ThemeToggle", () => {
  it("renders a labelled control", () => {
    renderWithProviders(<ThemeToggle />);
    expect(
      screen.getByRole("button", { name: messages.theme.toggle }),
    ).toBeInTheDocument();
  });

  it("cycles system → light → dark → system and persists each step", () => {
    renderWithProviders(<ThemeToggle />);
    const button = screen.getByRole("button", { name: messages.theme.toggle });

    // Starts at "system" (nothing stored).
    fireEvent.click(button);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);

    fireEvent.click(button);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    fireEvent.click(button);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("system");
  });

  it("reflects the active choice in its accessible state", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    renderWithProviders(<ThemeToggle />);
    // The current choice label is exposed for assistive tech / tooltip.
    expect(screen.getByText(messages.theme.dark)).toBeInTheDocument();
  });
});

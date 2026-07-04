"use client";

import { useTranslations } from "next-intl";

import { useTheme } from "@/lib/theme/use-theme";

/**
 * A compact control that cycles the color theme: system → light → dark → system.
 * The icon reflects the *chosen* mode (a monitor for "follow system", a sun for
 * light, a moon for dark); the chosen mode's label is exposed for assistive tech
 * and as a tooltip, while the button's accessible name states what it does.
 */
export function ThemeToggle() {
  const t = useTranslations("theme");
  const { choice, cycleTheme } = useTheme();

  return (
    <button
      type="button"
      onClick={cycleTheme}
      aria-label={t("toggle")}
      title={t(choice)}
      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border text-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ThemeIcon choice={choice} />
      <span className="sr-only">{t(choice)}</span>
    </button>
  );
}

function ThemeIcon({ choice }: { choice: "light" | "dark" | "system" }) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  if (choice === "light") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
    );
  }
  if (choice === "dark") {
    return (
      <svg {...common}>
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </svg>
  );
}

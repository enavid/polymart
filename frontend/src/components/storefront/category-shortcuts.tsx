"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import type { StorefrontCategory } from "@/lib/api/catalog";

/**
 * A curated palette of tasteful gradients cycled across the category discs. A
 * fixed set (rather than a random per-slug hue) keeps the row lively without
 * looking garish or unbranded, and it is deterministic so a category always
 * wears the same colour between renders.
 */
const TILE_GRADIENTS = [
  "linear-gradient(135deg,#6366f1,#8b5cf6)",
  "linear-gradient(135deg,#0ea5e9,#06b6d4)",
  "linear-gradient(135deg,#f59e0b,#f97316)",
  "linear-gradient(135deg,#ec4899,#f43f5e)",
  "linear-gradient(135deg,#10b981,#14b8a6)",
  "linear-gradient(135deg,#8b5cf6,#d946ef)",
];

/**
 * A horizontally scrollable row of circular category shortcuts -- the "jump
 * straight to a section" element every large storefront leads with. Each tile is
 * a link to the product listing pre-filtered to that category.
 *
 * Categories carry no imagery, so each disc wears a coloured gradient with the
 * category's monogram in white -- an intentional avatar rather than the muted
 * grey placeholder that reads as unfinished. Renders nothing when there are no
 * categories so the home page never shows an empty rail.
 */
export function CategoryShortcuts({ categories }: { categories: StorefrontCategory[] }) {
  const t = useTranslations("home");

  if (categories.length === 0) {
    return null;
  }

  return (
    <nav aria-label={t("categoriesTitle")} className="flex flex-col gap-4">
      <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">
        {t("categoriesTitle")}
      </h2>
      <ul className="flex gap-5 overflow-x-auto pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {categories.map((category, index) => {
          const monogram = Array.from(category.name.trim())[0] ?? "·";
          return (
            <li key={category.slug} className="shrink-0">
              <Link
                href={`/products?category=${encodeURIComponent(category.slug)}`}
                className="group flex w-20 flex-col items-center gap-2 rounded-lg focus-visible:outline-none"
              >
                <span
                  aria-hidden
                  style={{ backgroundImage: TILE_GRADIENTS[index % TILE_GRADIENTS.length] }}
                  className="flex h-16 w-16 items-center justify-center rounded-full text-2xl font-bold text-white shadow-sm transition group-hover:scale-105 group-hover:shadow-md group-focus-visible:ring-2 group-focus-visible:ring-ring group-focus-visible:ring-offset-2"
                >
                  {monogram}
                </span>
                <span className="line-clamp-2 text-center text-xs leading-snug text-foreground">
                  {category.name}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

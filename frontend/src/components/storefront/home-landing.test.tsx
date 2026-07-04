import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { HomeLanding } from "@/components/storefront/home-landing";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

type Product = { code: string; name: string; image?: { url: string; alt_text: string } };
type Category = { slug: string; name: string; parent: string | null };

/**
 * Wire the storefront reads the landing makes. The products endpoint answers the
 * curated strip (`collection=featured`) with `featured`; every other request
 * (the general fallback and the per-category strips) resolves empty, so tests
 * assert exactly one clean set of cards.
 */
function catalog({ featured = [], categories = [] }: { featured?: Product[]; categories?: Category[] } = {}) {
  server.use(
    http.get("*/catalog/storefront/categories/", () => HttpResponse.json(categories)),
    http.get("*/catalog/storefront/products/", ({ request }) => {
      const url = new URL(request.url);
      const results =
        url.searchParams.get("collection") === "featured" ? featured : [];
      return HttpResponse.json({
        count: results.length,
        limit: 12,
        offset: 0,
        results: results.map((r) => ({
          ...r,
          product_type: "coffee",
          values: [],
          metadata: {},
        })),
      });
    }),
  );
}

describe("HomeLanding", () => {
  it("shows the hero with a shop call-to-action", () => {
    catalog();
    renderWithProviders(<HomeLanding />);

    expect(
      screen.getByRole("heading", { name: messages.home.heroTitle }),
    ).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: messages.home.shopCta });
    expect(cta).toHaveAttribute("href", "/products");
  });

  it("renders featured products from the storefront read API", async () => {
    catalog({
      featured: [
        { code: "house-blend", name: "House Blend" },
        { code: "dark-roast", name: "Dark Roast" },
      ],
    });
    renderWithProviders(<HomeLanding />);

    expect(await screen.findByText("House Blend")).toBeInTheDocument();
    expect(screen.getByText("Dark Roast")).toBeInTheDocument();
    // Each product card is itself a link to that product's detail page.
    expect(screen.getByRole("link", { name: /House Blend/ })).toHaveAttribute(
      "href",
      "/products/house-blend",
    );
    expect(screen.getByRole("link", { name: /Dark Roast/ })).toHaveAttribute(
      "href",
      "/products/dark-roast",
    );
  });

  it("shows the empty state when there are no products", async () => {
    catalog();
    renderWithProviders(<HomeLanding />);

    expect(await screen.findByText(messages.home.featuredEmpty)).toBeInTheDocument();
  });

  it("offers a category shortcut linking to the filtered listing", async () => {
    catalog({ categories: [{ slug: "coffee-beans", name: "Coffee Beans", parent: null }] });
    renderWithProviders(<HomeLanding />);

    // The top-level category becomes a shortcut tile that deep-links into the PLP
    // pre-filtered to that category.
    const tile = await screen.findByRole("link", { name: /Coffee Beans/ });
    expect(tile).toHaveAttribute("href", "/products?category=coffee-beans");
  });

  it("does not give child categories their own shortcut", async () => {
    catalog({
      categories: [{ slug: "espresso", name: "Espresso", parent: "coffee-beans" }],
    });
    renderWithProviders(<HomeLanding />);

    // Wait for the trust strip (always rendered) so the category query has resolved.
    await screen.findByText(messages.home.trustAuthenticTitle);
    expect(screen.queryByRole("link", { name: /Espresso/ })).not.toBeInTheDocument();
  });

  it("always shows the reassurance strip", async () => {
    catalog();
    renderWithProviders(<HomeLanding />);

    expect(await screen.findByText(messages.home.trustAuthenticTitle)).toBeInTheDocument();
    expect(screen.getByText(messages.home.trustShippingTitle)).toBeInTheDocument();
  });

  it("offers a call-to-action band that links into the store", () => {
    catalog();
    renderWithProviders(<HomeLanding />);

    const cta = screen.getByRole("link", { name: messages.home.ctaButton });
    expect(cta).toHaveAttribute("href", "/products");
  });

  it("builds a hero collage from curated product photos", async () => {
    catalog({
      featured: [
        { code: "a", name: "Alpha", image: { url: "/a.jpg", alt_text: "Alpha shot" } },
        { code: "b", name: "Beta", image: { url: "/b.jpg", alt_text: "Beta shot" } },
      ],
    });
    renderWithProviders(<HomeLanding />);

    // The featured photo renders in both the hero collage and the grid below it.
    const shots = await screen.findAllByAltText("Alpha shot");
    expect(shots.length).toBeGreaterThan(1);
  });
});

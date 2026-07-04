import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { CategoryShortcuts } from "@/components/storefront/category-shortcuts";
import type { StorefrontCategory } from "@/lib/api/catalog";
import { renderWithProviders } from "@/test/utils";

function category(slug: string, name: string): StorefrontCategory {
  return { slug, name, parent: null };
}

describe("CategoryShortcuts", () => {
  it("links each category to the pre-filtered product listing", () => {
    renderWithProviders(
      <CategoryShortcuts categories={[category("coffee-beans", "Coffee Beans")]} />,
    );

    expect(screen.getByRole("link", { name: /Coffee Beans/ })).toHaveAttribute(
      "href",
      "/products?category=coffee-beans",
    );
  });

  it("encodes slugs that need escaping in the query string", () => {
    renderWithProviders(
      <CategoryShortcuts categories={[category("home & garden", "Home")]} />,
    );

    expect(screen.getByRole("link", { name: /Home/ })).toHaveAttribute(
      "href",
      "/products?category=home%20%26%20garden",
    );
  });

  it("renders nothing when there are no categories", () => {
    const { container } = renderWithProviders(<CategoryShortcuts categories={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});

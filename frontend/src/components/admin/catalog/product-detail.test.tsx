import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { ProductDetail } from "@/components/admin/catalog/product-detail";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const product = {
  id: 1,
  code: "house-blend",
  name: "House Blend",
  product_type: "coffee",
  values: [],
  metadata: {},
  is_published: false,
};

/** The reads the detail page makes: the product, its category membership, the
 *  full category list (for the chooser), and its variants. */
function detail({
  productBody = product,
  productCategories = [] as string[],
  categories = [] as { slug: string; name: string; parent: string | null }[],
} = {}) {
  server.use(
    http.get("*/catalog/products/house-blend/", () => HttpResponse.json(productBody)),
    http.get("*/catalog/products/house-blend/categories/", () =>
      HttpResponse.json({ categories: productCategories }),
    ),
    http.get("*/catalog/products/house-blend/variants/", () => HttpResponse.json([])),
    http.get("*/catalog/categories/", () => HttpResponse.json(categories)),
  );
}

describe("ProductDetail", () => {
  it("shows the product name", async () => {
    detail();

    renderWithProviders(<ProductDetail code="house-blend" />);

    expect((await screen.findAllByText("House Blend")).length).toBeGreaterThan(0);
  });

  it("toggles publication", async () => {
    let published = false;
    server.use(
      http.get("*/catalog/products/house-blend/", () =>
        HttpResponse.json({ ...product, is_published: published }),
      ),
      http.get("*/catalog/products/house-blend/categories/", () =>
        HttpResponse.json({ categories: [] }),
      ),
      http.get("*/catalog/products/house-blend/variants/", () => HttpResponse.json([])),
      http.get("*/catalog/categories/", () => HttpResponse.json([])),
      http.put("*/catalog/products/house-blend/publication/", () => {
        published = true;
        return HttpResponse.json({ ...product, is_published: true });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<ProductDetail code="house-blend" />);

    await user.click(
      await screen.findByRole("button", {
        name: messages.catalog.productDetail.publish,
      }),
    );

    expect(
      await screen.findByRole("button", {
        name: messages.catalog.productDetail.unpublish,
      }),
    ).toBeInTheDocument();
  });

  it("edits categories via checkboxes seeded from current membership", async () => {
    let saved: unknown = null;
    detail({
      productCategories: ["books"],
      categories: [
        { slug: "books", name: "Books", parent: null },
        { slug: "gifts", name: "Gifts", parent: null },
      ],
    });
    server.use(
      http.put("*/catalog/products/house-blend/categories/", async ({ request }) => {
        saved = await request.json();
        return HttpResponse.json({ categories: ["books", "gifts"] });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<ProductDetail code="house-blend" />);

    // The current membership is pre-checked; the other category is not.
    const books = (await screen.findByLabelText("Books")) as HTMLInputElement;
    const gifts = screen.getByLabelText("Gifts") as HTMLInputElement;
    expect(books.checked).toBe(true);
    expect(gifts.checked).toBe(false);

    await user.click(gifts);
    await user.click(screen.getByRole("button", { name: messages.catalog.save }));

    // Saving sends the chosen slugs, not a comma-separated string.
    expect(saved).toEqual({ categories: ["books", "gifts"] });
  });

  it("keeps the add-variant form collapsed until requested", async () => {
    detail();

    const user = userEvent.setup();
    renderWithProviders(<ProductDetail code="house-blend" />);

    // The SKU field only exists once the add-variant form is opened.
    await screen.findByText(messages.catalog.productDetail.noVariants);
    expect(screen.queryByLabelText(messages.catalog.productDetail.sku)).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: messages.catalog.productDetail.addVariant }),
    );
    expect(screen.getByLabelText(messages.catalog.productDetail.sku)).toBeInTheDocument();
  });
});

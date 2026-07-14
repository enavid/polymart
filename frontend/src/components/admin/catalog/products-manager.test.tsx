import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { ProductsManager } from "@/components/admin/catalog/products-manager";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const espresso = {
  id: 1,
  code: "espresso",
  name: "Espresso",
  product_type: "coffee",
  values: [],
  metadata: {},
  is_published: false,
  categories: [] as string[],
};

type Cat = { slug: string; name: string; parent: string | null };

/** Register the reads the manager makes: products, product-types (for the create
 *  form), and categories (for the filter + grouping). */
function catalog({
  products = [espresso],
  categories = [],
}: {
  products?: unknown[];
  categories?: Cat[];
} = {}) {
  server.use(
    http.get("*/catalog/products/", () => HttpResponse.json(products)),
    http.get("*/catalog/product-types/", () => HttpResponse.json([])),
    http.get("*/catalog/categories/", () => HttpResponse.json(categories)),
  );
}

describe("ProductsManager", () => {
  const uncategorized = messages.catalog.products.uncategorized;

  it("lists products with their status inside their category group", async () => {
    catalog();

    const user = userEvent.setup();
    renderWithProviders(<ProductsManager />);

    // Groups are collapsed by default; the product's code appears once its group opens.
    await user.click(await screen.findByRole("button", { name: new RegExp(uncategorized) }));
    expect(screen.getByText("espresso")).toBeInTheDocument();
    // The status badge is in the table (distinct from the status-filter option).
    expect(
      within(screen.getByRole("table")).getByText(messages.catalog.products.draft),
    ).toBeInTheDocument();
  });

  it("keeps the create form collapsed until asked", async () => {
    catalog();

    renderWithProviders(<ProductsManager />);

    // Wait for the list to resolve (the category group header appears).
    await screen.findByRole("button", { name: new RegExp(uncategorized) });
    // The list is the default view -- the code field only exists once the form opens.
    expect(screen.queryByLabelText(messages.catalog.code)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: messages.catalog.products.createTitle }),
    ).toBeInTheDocument();
  });

  it("filters the list by the search box", async () => {
    const latte = { ...espresso, code: "latte", name: "Latte" };
    catalog({ products: [espresso, latte] });

    const user = userEvent.setup();
    renderWithProviders(<ProductsManager />);

    // Open the group, then narrow it to a single product by typing.
    await user.click(await screen.findByRole("button", { name: new RegExp(uncategorized) }));
    expect(screen.getByText("espresso")).toBeInTheDocument();
    await user.type(
      screen.getByLabelText(messages.catalog.products.searchPlaceholder),
      "latte",
    );

    expect(screen.getByText("latte")).toBeInTheDocument();
    expect(screen.queryByText("espresso")).not.toBeInTheDocument();
  });

  it("groups products under their category, expanding on click", async () => {
    const beans = { ...espresso, code: "house", name: "House", categories: ["beans"] };
    catalog({
      products: [beans],
      categories: [{ slug: "beans", name: "Coffee Beans", parent: null }],
    });

    const user = userEvent.setup();
    renderWithProviders(<ProductsManager />);

    // The section is named after the category and starts collapsed (rows hidden).
    const header = await screen.findByRole("button", { name: /Coffee Beans/ });
    expect(screen.queryByText("house")).not.toBeInTheDocument();

    // Opening the group reveals its rows; closing it hides them again.
    await user.click(header);
    expect(screen.getByText("house")).toBeInTheDocument();
    await user.click(header);
    expect(screen.queryByText("house")).not.toBeInTheDocument();
  });

  it("filters products by the chosen category", async () => {
    const beans = { ...espresso, code: "house", name: "House", categories: ["beans"] };
    const tea = { ...espresso, code: "green", name: "Green", categories: ["tea"] };
    catalog({
      products: [beans, tea],
      categories: [
        { slug: "beans", name: "Coffee Beans", parent: null },
        { slug: "tea", name: "Tea", parent: null },
      ],
    });

    const user = userEvent.setup();
    renderWithProviders(<ProductsManager />);

    await screen.findByRole("button", { name: /Coffee Beans/ });
    await user.selectOptions(
      screen.getByLabelText(messages.catalog.products.filterCategory),
      "beans",
    );

    // Only the chosen category's group survives; the tea group is gone entirely.
    expect(screen.getByRole("button", { name: /Coffee Beans/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Tea/ })).not.toBeInTheDocument();
  });

  it("toggles a product's publication from its row's status badge", async () => {
    const put = vi.fn();
    let published = false;
    server.use(
      http.get("*/catalog/product-types/", () => HttpResponse.json([])),
      http.get("*/catalog/categories/", () => HttpResponse.json([])),
      http.get("*/catalog/products/", () =>
        HttpResponse.json([{ ...espresso, is_published: published }]),
      ),
      http.put("*/catalog/products/espresso/publication/", async ({ request }) => {
        put(await request.json());
        published = true;
        return HttpResponse.json({ ...espresso, is_published: true });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<ProductsManager />);

    // Open the group, then click the draft badge to publish inline.
    await user.click(await screen.findByRole("button", { name: new RegExp(uncategorized) }));
    await user.click(screen.getByRole("button", { name: messages.catalog.productDetail.publish }));

    await waitFor(() => expect(put).toHaveBeenCalledWith({ is_published: true }));
  });

  it("reveals the CSV import/export panel on demand", async () => {
    catalog();

    const user = userEvent.setup();
    renderWithProviders(<ProductsManager />);

    // The panel is not a separate section: it opens inline from the products page.
    await screen.findByRole("button", { name: new RegExp(uncategorized) });
    expect(
      screen.queryByRole("heading", { name: messages.catalog.importExport.title }),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: messages.catalog.navImportExport }),
    );
    expect(
      await screen.findByRole("heading", { name: messages.catalog.importExport.title }),
    ).toBeInTheDocument();
  });

  it("creates a product and refreshes the list", async () => {
    let created = false;
    let createdBody: Record<string, unknown> | null = null;
    server.use(
      http.get("*/catalog/product-types/", () =>
        HttpResponse.json([
          {
            id: 1,
            code: "coffee",
            name: "Coffee",
            attributes: [],
            variant_attributes: [],
          },
        ]),
      ),
      http.get("*/catalog/categories/", () => HttpResponse.json([])),
      http.get("*/catalog/products/", () =>
        HttpResponse.json(created ? [espresso] : []),
      ),
      http.post("*/catalog/products/", async ({ request }) => {
        created = true;
        createdBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(espresso, { status: 201 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<ProductsManager />);

    await screen.findByText(messages.catalog.products.empty);
    // The create form is collapsed by default; open it before filling it in.
    await user.click(
      screen.getByRole("button", { name: messages.catalog.products.createTitle }),
    );
    await user.type(screen.getByLabelText(messages.catalog.code), "espresso");
    await user.type(screen.getByLabelText(messages.catalog.name), "Espresso");
    await user.selectOptions(
      screen.getByLabelText(messages.catalog.products.productType),
      "coffee",
    );
    // Set a non-default tax class so the field is exercised.
    await user.clear(screen.getByLabelText(messages.catalog.products.taxClass));
    await user.type(screen.getByLabelText(messages.catalog.products.taxClass), "exempt");
    await user.click(
      screen.getByRole("button", { name: messages.catalog.create }),
    );

    // The refreshed list shows the new product's category group (uncategorized).
    expect(
      await screen.findByRole("button", { name: new RegExp(uncategorized) }),
    ).toBeInTheDocument();
    // The chosen tax class is submitted to the backend.
    expect(createdBody).toMatchObject({ tax_class: "exempt" });
  });
});

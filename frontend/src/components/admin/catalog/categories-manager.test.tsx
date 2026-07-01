import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { CategoriesManager } from "@/components/admin/catalog/categories-manager";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const beans = {
  id: 1,
  slug: "beans",
  name: "Beans",
  parent: null,
};

describe("CategoriesManager", () => {
  it("lists categories", async () => {
    server.use(
      http.get("*/catalog/categories/", () => HttpResponse.json([beans])),
    );

    renderWithProviders(<CategoriesManager />);

    // "Beans" (the name) appears only in the table; the slug "beans" also shows
    // up as a parent <select> option, so assert on the unique name.
    expect(await screen.findByText("Beans")).toBeInTheDocument();
  });

  it("creates a category and refreshes the list", async () => {
    let created = false;
    server.use(
      http.get("*/catalog/categories/", () =>
        HttpResponse.json(created ? [beans] : []),
      ),
      http.post("*/catalog/categories/", async () => {
        created = true;
        return HttpResponse.json(beans, { status: 201 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<CategoriesManager />);

    await screen.findByText(messages.catalog.categories.empty);
    await user.type(screen.getByLabelText(messages.catalog.slug), "beans");
    await user.type(screen.getByLabelText(messages.catalog.name), "Beans");
    await user.click(
      screen.getByRole("button", { name: messages.catalog.create }),
    );

    expect(await screen.findByText("Beans")).toBeInTheDocument();
  });
});

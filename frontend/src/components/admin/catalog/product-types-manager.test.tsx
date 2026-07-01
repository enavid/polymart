import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { ProductTypesManager } from "@/components/admin/catalog/product-types-manager";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const beverage = {
  id: 1,
  code: "beverage",
  name: "Beverage",
  attributes: ["origin"],
  variant_attributes: ["size"],
};

describe("ProductTypesManager", () => {
  it("lists product types with their fields", async () => {
    server.use(
      http.get("*/catalog/product-types/", () => HttpResponse.json([beverage])),
    );

    renderWithProviders(<ProductTypesManager />);

    expect(await screen.findByText("beverage")).toBeInTheDocument();
    expect(screen.getByText("Beverage")).toBeInTheDocument();
    expect(screen.getByText("origin")).toBeInTheDocument();
    expect(screen.getByText("size")).toBeInTheDocument();
  });

  it("shows an empty state when there are no product types", async () => {
    server.use(
      http.get("*/catalog/product-types/", () => HttpResponse.json([])),
    );

    renderWithProviders(<ProductTypesManager />);

    expect(
      await screen.findByText(messages.catalog.productTypes.empty),
    ).toBeInTheDocument();
  });

  it("creates a product type and refreshes the list", async () => {
    let created = false;
    server.use(
      http.get("*/catalog/product-types/", () =>
        HttpResponse.json(created ? [beverage] : []),
      ),
      http.post("*/catalog/product-types/", async () => {
        created = true;
        return HttpResponse.json(beverage, { status: 201 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<ProductTypesManager />);

    await screen.findByText(messages.catalog.productTypes.empty);
    await user.type(screen.getByLabelText(messages.catalog.code), "beverage");
    await user.type(screen.getByLabelText(messages.catalog.name), "Beverage");
    await user.click(
      screen.getByRole("button", { name: messages.catalog.create }),
    );

    expect(await screen.findByText("beverage")).toBeInTheDocument();
  });
});

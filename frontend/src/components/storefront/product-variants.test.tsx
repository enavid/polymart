import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { StorefrontProductVariants } from "@/components/storefront/product-variants";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const variants = {
  channel: "ir-main",
  variants: [
    {
      sku: "HB-250",
      name: "House Blend 250g",
      values: [{ attribute: "weight", value: "250" }],
      media: [],
      price: { amount: "120000.0000", currency: "IRR" },
    },
    {
      sku: "HB-500",
      name: "House Blend 500g",
      values: [],
      media: [],
      price: null,
    },
  ],
};

describe("StorefrontProductVariants", () => {
  it("lists variants with their price and an add button", async () => {
    server.use(
      http.get("*/catalog/storefront/products/house-blend/variants/", () =>
        HttpResponse.json(variants),
      ),
    );

    renderWithProviders(<StorefrontProductVariants code="house-blend" />);

    expect(await screen.findByText("House Blend 250g")).toBeInTheDocument();
    // The unpurchasable variant shows the unavailable label, not an add button.
    expect(screen.getAllByText(messages.storefront.unavailable).length).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("button", { name: messages.storefront.addToCart },
      ).length,
    ).toBe(1);
  });

  it("adds a variant to the cart and confirms", async () => {
    let body: unknown;
    server.use(
      http.get("*/catalog/storefront/products/house-blend/variants/", () =>
        HttpResponse.json(variants),
      ),
      http.post("*/cart/items/", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          channel: "ir-main",
          currency: "IRR",
          items: [
            {
              sku: "HB-250",
              quantity: 1,
              unit_price: "120000.0000",
              line_total: "120000.0000",
              available: true,
            },
          ],
          total: "120000.0000",
        });
      }),
    );

    renderWithProviders(<StorefrontProductVariants code="house-blend" />);
    const add = await screen.findByRole("button", {
      name: messages.storefront.addToCart,
    });
    await userEvent.click(add);

    expect(await screen.findByText(messages.storefront.added)).toBeInTheDocument();
    await waitFor(() =>
      expect(body).toEqual({ channel: "ir-main", sku: "HB-250", quantity: 1 }),
    );
  });

  it("shows an empty message when the product has no variants", async () => {
    server.use(
      http.get("*/catalog/storefront/products/house-blend/variants/", () =>
        HttpResponse.json({ channel: "ir-main", variants: [] }),
      ),
    );

    renderWithProviders(<StorefrontProductVariants code="house-blend" />);

    expect(await screen.findByText(messages.storefront.noVariants)).toBeInTheDocument();
  });
});

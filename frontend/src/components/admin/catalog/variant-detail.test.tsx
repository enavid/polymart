import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { VariantDetail } from "@/components/admin/catalog/variant-detail";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const variant = {
  id: 1,
  product: "house-blend",
  sku: "HB-001",
  name: "250g",
  values: [],
  media: [],
};

describe("VariantDetail", () => {
  it("shows the variant name and current stock", async () => {
    server.use(
      http.get("*/catalog/variants/HB-001/", () => HttpResponse.json(variant)),
      http.get("*/catalog/variants/HB-001/prices/", () =>
        HttpResponse.json({ prices: [] }),
      ),
      http.get("*/catalog/variants/HB-001/stock/", () => HttpResponse.json({ quantity: 5 })),
    );

    renderWithProviders(<VariantDetail sku="HB-001" />);

    expect((await screen.findAllByText("250g")).length).toBeGreaterThan(0);
    expect(await screen.findByText("5")).toBeInTheDocument();
  });

  it("sets the stock quantity", async () => {
    let quantity = 5;
    server.use(
      http.get("*/catalog/variants/HB-001/", () => HttpResponse.json(variant)),
      http.get("*/catalog/variants/HB-001/prices/", () =>
        HttpResponse.json({ prices: [] }),
      ),
      http.get("*/catalog/variants/HB-001/stock/", () =>
        HttpResponse.json({ quantity }),
      ),
      http.put("*/catalog/variants/HB-001/stock/", () => {
        quantity = 10;
        return HttpResponse.json({ quantity: 10 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<VariantDetail sku="HB-001" />);

    await screen.findAllByText("250g");
    await user.type(
      screen.getByLabelText(messages.catalog.variantDetail.quantity),
      "10",
    );
    await user.click(
      screen.getByRole("button", { name: messages.catalog.variantDetail.setStock }),
    );

    expect(await screen.findByText("10")).toBeInTheDocument();
  });
});

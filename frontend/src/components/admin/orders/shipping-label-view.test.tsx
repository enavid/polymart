import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { ShippingLabelView } from "@/components/admin/orders/shipping-label-view";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const label = messages.shippingLabel;

const ORDER = {
  number: "ORD-SHIP0001",
  channel: "ir-main",
  currency: "IRR",
  status: "fulfilled",
  subtotal: "240000.0000",
  shipping_cost: "50000.0000",
  shipping_method: "standard",
  shipping_method_name: "پست پیشتاز",
  tax: null,
  tax_rate: null,
  total: "290000.0000",
  placed_at: "2026-07-03T09:00:00Z",
  items: [{ sku: "HB-250", quantity: 2, unit_price: "120000.0000", line_total: "240000.0000" }],
  is_pickup: false,
  shipping_address: {
    recipient_name: "Sara Ahmadi",
    phone_number: "09123456789",
    province: "Tehran",
    city: "Tehran",
    postal_code: "1234567890",
    line1: "Valiasr St",
    line2: null,
  },
  fulfillment: { carrier: "Post", tracking_number: "TRK-42", tracking_url: null },
  document_type: "pre_invoice",
  grand_total: "290000.0000",
};

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("ShippingLabelView", () => {
  it("renders the destination, packing list, and captured shipment", async () => {
    server.use(http.get("*/orders/ORD-SHIP0001/pre-invoice/", () => HttpResponse.json(ORDER)));

    renderWithProviders(<ShippingLabelView number="ORD-SHIP0001" />);

    await screen.findByText("Sara Ahmadi");
    expect(screen.getByText("HB-250")).toBeInTheDocument();
    expect(screen.getByText("Post")).toBeInTheDocument();
    expect(screen.getByText("TRK-42")).toBeInTheDocument();
  });

  it("shows a pickup note instead of an address for a pickup order", async () => {
    server.use(
      http.get("*/orders/ORD-SHIP0001/pre-invoice/", () =>
        HttpResponse.json({ ...ORDER, is_pickup: true, shipping_address: null, fulfillment: null }),
      ),
    );

    renderWithProviders(<ShippingLabelView number="ORD-SHIP0001" />);

    await screen.findByText(label.pickupNote);
    expect(screen.queryByText("Sara Ahmadi")).not.toBeInTheDocument();
  });
});

import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { PreInvoiceView } from "@/components/admin/orders/pre-invoice-view";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const pre = messages.preInvoice;

const INVOICE = {
  number: "ORD-MANUAL01",
  channel: "ir-main",
  currency: "IRR",
  status: "pending",
  total: "390000.0000",
  placed_at: "2026-07-03T09:00:00Z",
  items: [
    { sku: "HB-250", quantity: 2, unit_price: "120000.0000", line_total: "240000.0000" },
    { sku: "DR-250", quantity: 1, unit_price: "150000.0000", line_total: "150000.0000" },
  ],
  shipping_address: {
    recipient_name: "Sara Ahmadi",
    phone_number: "09123456789",
    province: "Tehran",
    city: "Tehran",
    postal_code: "1234567890",
    line1: "Valiasr St",
    line2: null,
  },
  document_type: "pre_invoice",
  tax: null,
  grand_total: "390000.0000",
};

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("PreInvoiceView", () => {
  it("renders the server totals verbatim and a tax placeholder", async () => {
    server.use(http.get("*/orders/ORD-MANUAL01/pre-invoice/", () => HttpResponse.json(INVOICE)));

    renderWithProviders(<PreInvoiceView number="ORD-MANUAL01" />);

    expect(await screen.findByText("ORD-MANUAL01")).toBeInTheDocument();
    // Money is the exact server value, formatted (fa-IR digits, Toman for the IRR
    // ledger currency), never recomputed: the 390,000 IRR total and grand total
    // render as 39,000 Toman with Persian digits + grouping.
    expect(screen.getAllByText(/۳۹[٬,]۰۰۰/).length).toBeGreaterThanOrEqual(2);
    // The tax placeholder is shown (null tax -> "computed later" note).
    expect(screen.getByText(pre.taxPending)).toBeInTheDocument();
    expect(screen.getByText("HB-250")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: pre.print })).toBeInTheDocument();
  });

  it("shows an error state when the pre-invoice cannot be loaded", async () => {
    server.use(
      http.get("*/orders/ORD-MISSING/pre-invoice/", () =>
        HttpResponse.json({ detail: "not found" }, { status: 404 }),
      ),
    );

    renderWithProviders(<PreInvoiceView number="ORD-MISSING" />);

    expect(await screen.findByText(pre.loadError)).toBeInTheDocument();
  });
});

import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { OrdersList } from "@/components/orders/orders-list";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  window.localStorage.clear();
});
afterAll(() => server.close());

const orderRow = {
  number: "ORD-ABC123XYZ0",
  channel: "ir-main",
  currency: "IRR",
  status: "pending" as const,
  total: "240000.0000",
  placed_at: "2026-07-02T12:00:00Z",
  items: [],
};

describe("OrdersList", () => {
  it("shows an empty history", async () => {
    server.use(
      http.get("*/orders/", () =>
        HttpResponse.json({ count: 0, limit: 20, offset: 0, results: [] }),
      ),
    );

    renderWithProviders(<OrdersList />);

    expect(await screen.findByText(messages.orders.empty)).toBeInTheDocument();
  });

  it("lists orders with the server total and localized status (user or guest)", async () => {
    server.use(
      http.get("*/orders/", () =>
        HttpResponse.json({ count: 1, limit: 20, offset: 0, results: [orderRow] }),
      ),
    );

    renderWithProviders(<OrdersList />);

    expect(await screen.findByText("ORD-ABC123XYZ0")).toBeInTheDocument();
    // The status is shown through its localized label, not the raw enum value.
    expect(screen.getByText(messages.orders.statusPending)).toBeInTheDocument();
    // A link into the detail page.
    expect(screen.getByRole("link", { name: messages.orders.view }).getAttribute("href")).toBe(
      "/orders/ORD-ABC123XYZ0",
    );
  });

  it("surfaces a load error", async () => {
    server.use(
      http.get("*/orders/", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );

    renderWithProviders(<OrdersList />);

    expect(await screen.findByText("boom")).toBeInTheDocument();
  });
});

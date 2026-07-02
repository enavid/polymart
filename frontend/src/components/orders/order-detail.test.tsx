import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { OrderDetail } from "@/components/orders/order-detail";
import { markSignedIn } from "@/lib/auth/session-hint";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  window.localStorage.clear();
});
afterAll(() => server.close());

function authed() {
  markSignedIn();
  server.use(
    http.get("*/auth/me/", () =>
      HttpResponse.json({
        id: 7,
        phone_number: "+989120000001",
        email: "",
        full_name: "Shopper",
        is_staff: false,
      }),
    ),
  );
}

const NUMBER = "ORD-ABC123XYZ0";

function order(overrides: Record<string, unknown> = {}) {
  return {
    number: NUMBER,
    channel: "ir-main",
    currency: "IRR",
    status: "pending",
    total: "240000.0000",
    placed_at: "2026-07-02T12:00:00Z",
    items: [
      { sku: "HB-250", quantity: 2, unit_price: "120000.0000", line_total: "240000.0000" },
    ],
    ...overrides,
  };
}

describe("OrderDetail", () => {
  it("renders the captured lines and server total", async () => {
    authed();
    server.use(http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order())));

    renderWithProviders(<OrderDetail number={NUMBER} />);

    expect(await screen.findByText("HB-250")).toBeInTheDocument();
    // The total shown is the backend string, formatted -- never recomputed client-side.
    expect(screen.getByText(messages.orders.total)).toBeInTheDocument();
    expect(screen.getByText(messages.orders.statusPending)).toBeInTheDocument();
  });

  it("shows a not-found message for another user's / missing order (404)", async () => {
    authed();
    server.use(
      http.get(`*/orders/${NUMBER}/`, () =>
        HttpResponse.json({ detail: "order not found" }, { status: 404 }),
      ),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    expect(await screen.findByText(messages.orders.notFound)).toBeInTheDocument();
  });

  it("cancels a pending order after inline confirmation", async () => {
    authed();
    let cancelled = false;
    server.use(
      http.get(`*/orders/${NUMBER}/`, () =>
        HttpResponse.json(cancelled ? order({ status: "cancelled" }) : order()),
      ),
      http.post(`*/orders/${NUMBER}/cancel/`, () => {
        cancelled = true;
        return HttpResponse.json(order({ status: "cancelled" }));
      }),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    // First click reveals the inline confirmation (no native dialog).
    const cancelBtn = await screen.findByRole("button", { name: messages.orders.cancel });
    await userEvent.click(cancelBtn);
    expect(screen.getByText(messages.orders.cancelConfirm)).toBeInTheDocument();

    // Confirm.
    await userEvent.click(screen.getByRole("button", { name: messages.orders.cancel }));

    expect(await screen.findByText(messages.orders.cancelledNote)).toBeInTheDocument();
  });

  it("does not offer cancel for a non-pending order", async () => {
    authed();
    server.use(
      http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order({ status: "paid" }))),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    await screen.findByText(messages.orders.statusPaid);
    expect(
      screen.queryByRole("button", { name: messages.orders.cancel }),
    ).not.toBeInTheDocument();
  });

  it("surfaces a cancel conflict (409) without hiding the order", async () => {
    authed();
    server.use(
      http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order())),
      http.post(`*/orders/${NUMBER}/cancel/`, () =>
        HttpResponse.json({ detail: "cannot cancel" }, { status: 409 }),
      ),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    await userEvent.click(await screen.findByRole("button", { name: messages.orders.cancel }));
    await userEvent.click(screen.getByRole("button", { name: messages.orders.cancel }));

    expect(await screen.findByText("cannot cancel")).toBeInTheDocument();
  });
});

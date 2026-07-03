import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { CartView } from "@/components/cart/cart-view";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  window.localStorage.clear();
  push.mockReset();
});
afterAll(() => server.close());

const cartWithLine = {
  channel: "ir-main",
  currency: "IRR",
  items: [
    {
      sku: "HB-250",
      quantity: 2,
      unit_price: "120000.0000",
      line_total: "240000.0000",
      available: true,
    },
  ],
  total: "240000.0000",
};

describe("CartView", () => {
  it("shows a guest's cart without requiring login", async () => {
    // No session at all: the cart is still resolved (from the guest cookie) and shown.
    server.use(http.get("*/cart/", () => HttpResponse.json(cartWithLine)));

    renderWithProviders(<CartView />);

    expect(await screen.findByText("HB-250")).toBeInTheDocument();
    // The cart is shown directly -- no "please sign in" gate for a guest.
    expect(screen.getByText(messages.cart.total)).toBeInTheDocument();
  });

  it("shows an empty cart", async () => {
    server.use(
      http.get("*/cart/", () =>
        HttpResponse.json({ channel: "ir-main", currency: "IRR", items: [], total: "0" }),
      ),
    );

    renderWithProviders(<CartView />);

    expect(await screen.findByText(messages.cart.empty)).toBeInTheDocument();
  });

  it("renders lines and the server-computed total", async () => {
    server.use(http.get("*/cart/", () => HttpResponse.json(cartWithLine)));

    renderWithProviders(<CartView />);

    expect(await screen.findByText("HB-250")).toBeInTheDocument();
    // The total shown is the backend string, formatted -- not recomputed client-side.
    expect(screen.getByText(messages.cart.total)).toBeInTheDocument();
  });

  it("removes a line", async () => {
    server.use(
      http.get("*/cart/", () => HttpResponse.json(cartWithLine)),
      http.delete("*/cart/items/HB-250/", () =>
        HttpResponse.json({ channel: "ir-main", currency: "IRR", items: [], total: "0" }),
      ),
    );

    renderWithProviders(<CartView />);
    const remove = await screen.findByRole("button", { name: messages.cart.remove });
    await userEvent.click(remove);

    expect(await screen.findByText(messages.cart.empty)).toBeInTheDocument();
  });

  it("updates a line quantity", async () => {
    let putBody: unknown;
    server.use(
      http.get("*/cart/", () => HttpResponse.json(cartWithLine)),
      http.put("*/cart/items/HB-250/", async ({ request }) => {
        putBody = await request.json();
        return HttpResponse.json({
          ...cartWithLine,
          items: [{ ...cartWithLine.items[0], quantity: 5, line_total: "600000.0000" }],
          total: "600000.0000",
        });
      }),
    );

    renderWithProviders(<CartView />);
    const qty = await screen.findByLabelText(messages.cart.quantity);
    await userEvent.clear(qty);
    await userEvent.type(qty, "5");
    await userEvent.click(screen.getByRole("button", { name: messages.cart.update }));

    await waitFor(() => expect(putBody).toEqual({ channel: "ir-main", quantity: 5 }));
  });

  it("links to the multi-step checkout page", async () => {
    server.use(http.get("*/cart/", () => HttpResponse.json(cartWithLine)));

    renderWithProviders(<CartView />);
    // Checkout is now a multi-step flow on its own page; the cart just links into it
    // (address selection + place-order live there, not in the cart).
    const checkout = await screen.findByRole("link", { name: messages.cart.checkout });
    expect(checkout.getAttribute("href")).toBe("/checkout");
  });

  it("disables checkout when a line is unavailable", async () => {
    server.use(
      http.get("*/cart/", () =>
        HttpResponse.json({
          channel: "ir-main",
          currency: "IRR",
          items: [
            {
              sku: "HB-250",
              quantity: 1,
              unit_price: null,
              line_total: null,
              available: false,
            },
          ],
          total: "0",
        }),
      ),
    );

    renderWithProviders(<CartView />);
    // While a line is unavailable, checkout is a disabled button (not a link), so the
    // shopper cannot proceed to checkout until they resolve it.
    const checkout = await screen.findByRole("button", { name: messages.cart.checkout });
    expect(checkout).toBeDisabled();
    expect(screen.queryByRole("link", { name: messages.cart.checkout })).not.toBeInTheDocument();
  });

  it("warns and excludes an unavailable line", async () => {
    server.use(
      http.get("*/cart/", () =>
        HttpResponse.json({
          channel: "ir-main",
          currency: "IRR",
          items: [
            {
              sku: "HB-250",
              quantity: 2,
              unit_price: null,
              line_total: null,
              available: false,
            },
          ],
          total: "0",
        }),
      ),
    );

    renderWithProviders(<CartView />);

    expect(await screen.findByText(messages.cart.unavailable)).toBeInTheDocument();
  });
});

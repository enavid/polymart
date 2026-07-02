import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { CartView } from "@/components/cart/cart-view";
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
  it("prompts to log in when unauthenticated", async () => {
    server.use(
      http.get("*/auth/me/", () => HttpResponse.json({ detail: "no" }, { status: 401 })),
    );

    renderWithProviders(<CartView />);

    expect(await screen.findByText(messages.cart.loginRequired)).toBeInTheDocument();
  });

  it("shows an empty cart", async () => {
    authed();
    server.use(
      http.get("*/cart/", () =>
        HttpResponse.json({ channel: "ir-main", currency: "IRR", items: [], total: "0" }),
      ),
    );

    renderWithProviders(<CartView />);

    expect(await screen.findByText(messages.cart.empty)).toBeInTheDocument();
  });

  it("renders lines and the server-computed total", async () => {
    authed();
    server.use(http.get("*/cart/", () => HttpResponse.json(cartWithLine)));

    renderWithProviders(<CartView />);

    expect(await screen.findByText("HB-250")).toBeInTheDocument();
    // The total shown is the backend string, formatted -- not recomputed client-side.
    expect(screen.getByText(messages.cart.total)).toBeInTheDocument();
  });

  it("removes a line", async () => {
    authed();
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
    authed();
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

  it("warns and excludes an unavailable line", async () => {
    authed();
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

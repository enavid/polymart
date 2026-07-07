import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { CheckoutView } from "@/components/checkout/checkout-view";
import { markSignedIn } from "@/lib/auth/session-hint";
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
    // Default: an empty wallet, so the checkout's wallet read is always satisfied and the
    // pay-with-wallet option is not offered. Tests that need a funded wallet override this.
    http.get("*/wallet/", () =>
      HttpResponse.json({ balance: "0", currency: "IRR", transactions: [] }),
    ),
  );
}

/** A funded wallet read for the pay-with-wallet tests. */
function walletBalance(balance: string) {
  return http.get("*/wallet/", () =>
    HttpResponse.json({ balance, currency: "IRR", transactions: [] }),
  );
}

/** A captured wallet-payment initiation (settled instantly; next_action "none"). */
function walletInitiation(orderNumber: string) {
  return HttpResponse.json(
    {
      reference: "PAY-WALLET00001",
      order_number: orderNumber,
      method: "wallet",
      amount: "240000.0000",
      currency: "IRR",
      status: "captured",
      created_at: "2026-07-02T12:00:00Z",
      next_action: "none",
      redirect_url: null,
    },
    { status: 201 },
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

const savedAddress = {
  id: "ADDR-HOME000001",
  recipient_name: "Sara Ahmadi",
  phone_number: "+989123456789",
  province: "Tehran",
  city: "Tehran",
  postal_code: "1234567890",
  line1: "Valiasr St, No. 1",
  line2: null,
  is_default: true,
  created_at: "2026-07-02T12:00:00Z",
};

const checkout = messages.checkout;

const addresses = messages.addresses;

const payment = messages.payment;

/** A COD initiation response for the just-placed order (next_action "none"). */
function codInitiation(orderNumber: string) {
  return HttpResponse.json(
    {
      reference: "PAY-ABC123XYZ00",
      order_number: orderNumber,
      method: "cod",
      amount: "240000.0000",
      currency: "IRR",
      status: "pending",
      created_at: "2026-07-02T12:00:00Z",
      next_action: "none",
      redirect_url: null,
    },
    { status: 201 },
  );
}

describe("CheckoutView", () => {
  it("lets a guest check out with an inline shipping address (no login)", async () => {
    // No session: the guest sees an inline shipping form instead of an address book,
    // and the order is placed with that captured address (never an address_id).
    let placedBody: unknown;
    server.use(
      http.get("*/cart/", () => HttpResponse.json(cartWithLine)),
      http.post("*/orders/", async ({ request }) => {
        placedBody = await request.json();
        return HttpResponse.json(
          {
            number: "ORD-GUEST00001",
            channel: "ir-main",
            currency: "IRR",
            status: "pending",
            total: "240000.0000",
            placed_at: "2026-07-02T12:00:00Z",
            items: [],
            shipping_address: {
              recipient_name: "Guest Buyer",
              phone_number: "09121112233",
              province: "Isfahan",
              city: "Isfahan",
              postal_code: "8134567890",
              line1: "Chaharbagh St, No. 9",
              line2: null,
            },
          },
          { status: 201 },
        );
      }),
      http.post("*/payments/", () => codInitiation("ORD-GUEST00001")),
    );

    renderWithProviders(<CheckoutView />);

    // The guest is not asked to log in; they fill the one-off shipping form.
    await userEvent.type(
      await screen.findByLabelText(addresses.recipientName),
      "Guest Buyer",
    );
    await userEvent.type(screen.getByLabelText(addresses.phoneNumber), "09121112233");
    await userEvent.type(screen.getByLabelText(addresses.province), "Isfahan");
    await userEvent.type(screen.getByLabelText(addresses.city), "Isfahan");
    await userEvent.type(screen.getByLabelText(addresses.postalCode), "8134567890");
    await userEvent.type(screen.getByLabelText(addresses.line1), "Chaharbagh St, No. 9");
    await userEvent.click(screen.getByRole("button", { name: addresses.save }));

    // Review step: a guest is never offered pay-with-wallet (no account, no wallet).
    await screen.findByRole("button", { name: checkout.placeOrder });
    expect(
      screen.queryByLabelText(payment.methodWallet, { exact: false }),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: checkout.placeOrder }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/orders/ORD-GUEST00001"));
    // A one-off inline address is submitted -- never an address_id (a guest has no book).
    expect(placedBody).toEqual({
      channel: "ir-main",
      shipping_address: {
        recipient_name: "Guest Buyer",
        phone_number: "09121112233",
        province: "Isfahan",
        city: "Isfahan",
        postal_code: "8134567890",
        line1: "Chaharbagh St, No. 9",
      },
    });
  });

  it("shows the empty-cart state", async () => {
    authed();
    server.use(
      http.get("*/cart/", () =>
        HttpResponse.json({ channel: "ir-main", currency: "IRR", items: [], total: "0" }),
      ),
      http.get("*/addresses/", () => HttpResponse.json([savedAddress])),
    );

    renderWithProviders(<CheckoutView />);

    expect(await screen.findByText(checkout.emptyCart)).toBeInTheDocument();
  });

  it("preselects the default address and places an order to it", async () => {
    authed();
    let placedBody: unknown;
    server.use(
      http.get("*/cart/", () => HttpResponse.json(cartWithLine)),
      http.get("*/addresses/", () => HttpResponse.json([savedAddress])),
      http.post("*/orders/", async ({ request }) => {
        placedBody = await request.json();
        return HttpResponse.json(
          {
            number: "ORD-ABC123XYZ0",
            channel: "ir-main",
            currency: "IRR",
            status: "pending",
            total: "240000.0000",
            placed_at: "2026-07-02T12:00:00Z",
            items: [],
            shipping_address: { ...savedAddress },
          },
          { status: 201 },
        );
      }),
      http.post("*/payments/", () => codInitiation("ORD-ABC123XYZ0")),
    );

    renderWithProviders(<CheckoutView />);

    // The saved address is shown and preselected; continue to review.
    await screen.findByText("Sara Ahmadi");
    await userEvent.click(screen.getByRole("button", { name: checkout.continue }));

    // Review step: place the order.
    const placeButton = await screen.findByRole("button", { name: checkout.placeOrder });
    await userEvent.click(placeButton);

    await waitFor(() => expect(push).toHaveBeenCalledWith("/orders/ORD-ABC123XYZ0"));
    // The chosen saved address id is what was submitted (a snapshot is captured server-side).
    expect(placedBody).toEqual({ channel: "ir-main", address_id: "ADDR-HOME000001" });
  });

  it("initiates a COD payment for the placed order and shows the method choices", async () => {
    authed();
    let paidBody: unknown;
    server.use(
      http.get("*/cart/", () => HttpResponse.json(cartWithLine)),
      http.get("*/addresses/", () => HttpResponse.json([savedAddress])),
      http.post("*/orders/", () =>
        HttpResponse.json(
          {
            number: "ORD-ABC123XYZ0",
            channel: "ir-main",
            currency: "IRR",
            status: "pending",
            total: "240000.0000",
            placed_at: "2026-07-02T12:00:00Z",
            items: [],
            shipping_address: { ...savedAddress },
          },
          { status: 201 },
        ),
      ),
      http.post("*/payments/", async ({ request }) => {
        paidBody = await request.json();
        return codInitiation("ORD-ABC123XYZ0");
      }),
    );

    renderWithProviders(<CheckoutView />);
    await screen.findByText("Sara Ahmadi");
    await userEvent.click(screen.getByRole("button", { name: checkout.continue }));

    // The review step offers COD (default), online, and card-to-card -- all selectable now.
    // Labels wrap hint/badge text, so match as a substring.
    const cod = await screen.findByLabelText(payment.methodCod, { exact: false });
    expect(cod).toBeChecked();
    expect(screen.getByLabelText(payment.methodOnline, { exact: false })).toBeEnabled();
    expect(screen.getByLabelText(payment.methodCardToCard, { exact: false })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: checkout.placeOrder }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/orders/ORD-ABC123XYZ0"));
    // The chosen method (COD) is initiated against the just-placed order.
    expect(paidBody).toEqual({ order_number: "ORD-ABC123XYZ0", method: "cod" });
  });

  it("redirects to the gateway when the online method is chosen", async () => {
    authed();
    const assign = vi.fn();
    // jsdom's window.location.assign is not implemented; replace it for this test.
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, assign },
    });
    let paidBody: unknown;
    server.use(
      http.get("*/cart/", () => HttpResponse.json(cartWithLine)),
      http.get("*/addresses/", () => HttpResponse.json([savedAddress])),
      http.post("*/orders/", () =>
        HttpResponse.json(
          {
            number: "ORD-ONLINE0001",
            channel: "ir-main",
            currency: "IRR",
            status: "pending",
            total: "240000.0000",
            placed_at: "2026-07-02T12:00:00Z",
            items: [],
            shipping_address: { ...savedAddress },
          },
          { status: 201 },
        ),
      ),
      http.post("*/payments/", async ({ request }) => {
        paidBody = await request.json();
        return HttpResponse.json(
          {
            reference: "PAY-ONLINE00001",
            order_number: "ORD-ONLINE0001",
            method: "online",
            amount: "240000.0000",
            currency: "IRR",
            status: "pending",
            created_at: "2026-07-02T12:00:00Z",
            next_action: "redirect",
            redirect_url: "/api/v1/payments/mock-gateway/?authority=MOCK-PAY-ONLINE00001",
          },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<CheckoutView />);
    await screen.findByText("Sara Ahmadi");
    await userEvent.click(screen.getByRole("button", { name: checkout.continue }));

    // Choose online, then place the order.
    await userEvent.click(await screen.findByLabelText(payment.methodOnline, { exact: false }));
    await userEvent.click(screen.getByRole("button", { name: checkout.placeOrder }));

    // The browser is handed off to the gateway URL; it does NOT navigate to the order yet.
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith(
        "/api/v1/payments/mock-gateway/?authority=MOCK-PAY-ONLINE00001",
      ),
    );
    expect(paidBody).toEqual({ order_number: "ORD-ONLINE0001", method: "online" });
    expect(push).not.toHaveBeenCalled();
  });

  it("offers pay-with-wallet when the balance covers the order and settles it instantly", async () => {
    authed();
    let paidBody: unknown;
    server.use(
      http.get("*/cart/", () => HttpResponse.json(cartWithLine)),
      http.get("*/addresses/", () => HttpResponse.json([savedAddress])),
      walletBalance("300000.0000"), // covers the 240000 order total
      http.post("*/orders/", () =>
        HttpResponse.json(
          {
            number: "ORD-WALLET0001",
            channel: "ir-main",
            currency: "IRR",
            status: "pending",
            total: "240000.0000",
            placed_at: "2026-07-02T12:00:00Z",
            items: [],
            shipping_address: { ...savedAddress },
          },
          { status: 201 },
        ),
      ),
      http.post("*/payments/", async ({ request }) => {
        paidBody = await request.json();
        return walletInitiation("ORD-WALLET0001");
      }),
    );

    renderWithProviders(<CheckoutView />);
    await screen.findByText("Sara Ahmadi");
    await userEvent.click(screen.getByRole("button", { name: checkout.continue }));

    // The wallet option is offered and selectable (the balance covers the total).
    const walletOption = await screen.findByLabelText(payment.methodWallet, { exact: false });
    expect(walletOption).toBeEnabled();
    await userEvent.click(walletOption);
    await userEvent.click(screen.getByRole("button", { name: checkout.placeOrder }));

    // A captured wallet payment is settled server-side; the shopper lands on the paid order.
    await waitFor(() => expect(push).toHaveBeenCalledWith("/orders/ORD-WALLET0001"));
    expect(paidBody).toEqual({ order_number: "ORD-WALLET0001", method: "wallet" });
  });

  it("shows pay-with-wallet disabled when the balance is short", async () => {
    authed();
    server.use(
      http.get("*/cart/", () => HttpResponse.json(cartWithLine)),
      http.get("*/addresses/", () => HttpResponse.json([savedAddress])),
      walletBalance("100000.0000"), // some credit, but less than the 240000 total
    );

    renderWithProviders(<CheckoutView />);
    await screen.findByText("Sara Ahmadi");
    await userEvent.click(screen.getByRole("button", { name: checkout.continue }));

    // The option is shown (there is some credit) but not selectable, with an explanation.
    const walletOption = await screen.findByLabelText(payment.methodWallet, { exact: false });
    expect(walletOption).toBeDisabled();
    expect(screen.getByText(payment.walletInsufficient)).toBeInTheDocument();
  });

  it("surfaces a place-order conflict (e.g. oversell) without navigating", async () => {
    authed();
    server.use(
      http.get("*/cart/", () => HttpResponse.json(cartWithLine)),
      http.get("*/addresses/", () => HttpResponse.json([savedAddress])),
      http.post("*/orders/", () =>
        HttpResponse.json({ detail: "insufficient stock" }, { status: 409 }),
      ),
    );

    renderWithProviders(<CheckoutView />);
    await screen.findByText("Sara Ahmadi");
    await userEvent.click(screen.getByRole("button", { name: checkout.continue }));
    await userEvent.click(await screen.findByRole("button", { name: checkout.placeOrder }));

    // The raw backend detail is not shopper-appropriate; a localized message is shown.
    expect(await screen.findByText(checkout.placeError)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("forces the add-address form when the shopper has no saved addresses", async () => {
    authed();
    let created = false;
    server.use(
      http.get("*/cart/", () => HttpResponse.json(cartWithLine)),
      http.get("*/addresses/", () => HttpResponse.json(created ? [savedAddress] : [])),
      http.post("*/addresses/", () => {
        created = true;
        return HttpResponse.json(savedAddress, { status: 201 });
      }),
    );

    renderWithProviders(<CheckoutView />);

    // With no saved addresses, the form is shown directly (no continue yet).
    const nameField = await screen.findByLabelText(messages.addresses.recipientName);
    expect(screen.queryByRole("button", { name: checkout.continue })).not.toBeInTheDocument();

    await userEvent.type(nameField, "Sara Ahmadi");
    await userEvent.type(screen.getByLabelText(messages.addresses.phoneNumber), "09123456789");
    await userEvent.type(screen.getByLabelText(messages.addresses.province), "Tehran");
    await userEvent.type(screen.getByLabelText(messages.addresses.city), "Tehran");
    await userEvent.type(screen.getByLabelText(messages.addresses.postalCode), "1234567890");
    await userEvent.type(screen.getByLabelText(messages.addresses.line1), "Valiasr St, No. 1");
    await userEvent.click(screen.getByRole("button", { name: messages.addresses.save }));

    // After saving, the address appears as a selectable option and we can continue.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: checkout.continue })).toBeInTheDocument(),
    );
  });

  it("blocks checkout when a cart line is unavailable", async () => {
    authed();
    server.use(
      http.get("*/cart/", () =>
        HttpResponse.json({
          channel: "ir-main",
          currency: "IRR",
          items: [
            { sku: "HB-250", quantity: 1, unit_price: null, line_total: null, available: false },
          ],
          total: "0",
        }),
      ),
      http.get("*/addresses/", () => HttpResponse.json([savedAddress])),
    );

    renderWithProviders(<CheckoutView />);

    expect(await screen.findByText(checkout.unavailableBlocked)).toBeInTheDocument();
    // Cannot continue to review while a line is unavailable.
    expect(screen.getByRole("button", { name: checkout.continue })).toBeDisabled();
  });
});

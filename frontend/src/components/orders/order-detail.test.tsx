import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen, waitFor, waitForElementToBeRemoved, within } from "@testing-library/react";
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

const NUMBER = "ORD-ABC123XYZ0";

/** A COD payment for the order (used as the default in `authed`). */
function codPayment(overrides: Record<string, unknown> = {}) {
  return {
    reference: "PAY-ABC123XYZ00",
    order_number: NUMBER,
    method: "cod",
    amount: "240000.0000",
    currency: "IRR",
    status: "pending",
    created_at: "2026-07-02T12:00:00Z",
    transfer_reference: null,
    ...overrides,
  };
}

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
    // The order-detail page reads the order's payment; default to a COD one so every
    // test has it. Tests about the payment block itself override this handler.
    http.get(`*/payments/for-order/${NUMBER}/`, () => HttpResponse.json(codPayment())),
  );
}

function order(overrides: Record<string, unknown> = {}) {
  return {
    number: NUMBER,
    channel: "ir-main",
    currency: "IRR",
    status: "pending",
    // Grand total = goods 240000 + standard shipping 50000.
    subtotal: "240000.0000",
    shipping_cost: "50000.0000",
    shipping_method: "standard",
    shipping_method_name: "پست پیشتاز",
    total: "290000.0000",
    placed_at: "2026-07-02T12:00:00Z",
    items: [
      { sku: "HB-250", quantity: 2, unit_price: "120000.0000", line_total: "240000.0000" },
    ],
    shipping_address: {
      recipient_name: "Sara Ahmadi",
      phone_number: "+989123456789",
      province: "Tehran",
      city: "Tehran",
      postal_code: "1234567890",
      line1: "Valiasr St, No. 1",
      line2: null,
    },
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
    // The order-status label appears in the timeline (the payment status shares the same
    // Persian text, so scope this to the timeline list).
    const timeline = screen.getByRole("list", { name: messages.orders.timeline });
    expect(within(timeline).getByText(messages.orders.statusPending)).toBeInTheDocument();
    // The captured shipping address is shown.
    expect(screen.getByText(messages.orders.shippingAddress)).toBeInTheDocument();
    expect(screen.getByText("Sara Ahmadi")).toBeInTheDocument();
    // The order shows the subtotal / shipping / total breakdown (server values, not recomputed).
    expect(screen.getByText(messages.orders.subtotal)).toBeInTheDocument();
    expect(screen.getByText("پست پیشتاز", { exact: false })).toBeInTheDocument();
    // 290000 IRR grand total -> 29000 Toman.
    expect(screen.getByText("۲۹٬۰۰۰ تومان")).toBeInTheDocument();
  });

  it("shows the payment method and status block", async () => {
    authed();
    server.use(http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order())));

    renderWithProviders(<OrderDetail number={NUMBER} />);

    const heading = await screen.findByText(messages.payment.sectionTitle);
    const section = heading.closest("section") as HTMLElement;
    expect(within(section).getByText(messages.payment.methodCod)).toBeInTheDocument();
    // The payment status (pending) is shown via its localized label, scoped to the block.
    expect(within(section).getByText(messages.payment.statusPending)).toBeInTheDocument();
  });

  it("shows a muted note when the order has no payment (404)", async () => {
    authed();
    server.use(
      http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order())),
      http.get(`*/payments/for-order/${NUMBER}/`, () =>
        HttpResponse.json({ detail: "payment not found" }, { status: 404 }),
      ),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    // The order still renders; the payment section shows the "none" note, not an error.
    expect(await screen.findByText("HB-250")).toBeInTheDocument();
    expect(await screen.findByText(messages.payment.none)).toBeInTheDocument();
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

  /** Sign in as a staff member (the refund control is staff-only). */
  function staffAuthed(payment: Record<string, unknown>) {
    markSignedIn();
    server.use(
      http.get("*/auth/me/", () =>
        HttpResponse.json({
          id: 1,
          phone_number: "+989120000009",
          email: "",
          full_name: "Staff",
          is_staff: true,
        }),
      ),
      http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order({ status: "paid" }))),
      http.get(`*/payments/for-order/${NUMBER}/`, () => HttpResponse.json(payment)),
    );
  }

  it("lets staff refund a captured payment to the wallet", async () => {
    let refunded = false;
    staffAuthed(codPayment({ method: "online", status: "captured" }));
    server.use(
      // The payment re-reads as refunded once the refund POST has landed.
      http.get(`*/payments/for-order/${NUMBER}/`, () =>
        HttpResponse.json(
          codPayment({ method: "online", status: refunded ? "refunded" : "captured" }),
        ),
      ),
      http.post("*/payments/PAY-ABC123XYZ00/refund/", () => {
        refunded = true;
        return HttpResponse.json(codPayment({ method: "online", status: "refunded" }));
      }),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    const button = await screen.findByRole("button", {
      name: messages.payment.refundToWallet,
    });
    await userEvent.click(button);

    // After the refund lands, the payment shows refunded and the control disappears.
    expect(await screen.findByText(messages.payment.statusRefunded)).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: messages.payment.refundToWallet }),
      ).not.toBeInTheDocument(),
    );
  });

  it("does not show the refund control to a non-staff shopper", async () => {
    authed();
    server.use(
      http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order({ status: "paid" }))),
      http.get(`*/payments/for-order/${NUMBER}/`, () =>
        HttpResponse.json(codPayment({ method: "online", status: "captured" })),
      ),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    await screen.findByText(messages.payment.statusCaptured);
    expect(
      screen.queryByRole("button", { name: messages.payment.refundToWallet }),
    ).not.toBeInTheDocument();
  });

  it("does not show the refund control for a non-captured payment", async () => {
    staffAuthed(codPayment({ method: "cod", status: "pending" }));

    renderWithProviders(<OrderDetail number={NUMBER} />);

    await screen.findByText(messages.payment.statusPending);
    expect(
      screen.queryByRole("button", { name: messages.payment.refundToWallet }),
    ).not.toBeInTheDocument();
  });

  it("surfaces a refund conflict (409) without losing the control", async () => {
    staffAuthed(codPayment({ method: "online", status: "captured" }));
    server.use(
      http.post("*/payments/PAY-ABC123XYZ00/refund/", () =>
        HttpResponse.json({ detail: "not refundable" }, { status: 409 }),
      ),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    await userEvent.click(
      await screen.findByRole("button", { name: messages.payment.refundToWallet }),
    );

    expect(await screen.findByText("not refundable")).toBeInTheDocument();
  });

  // --- Card-to-card ------------------------------------------------------

  const CARD = { card_number: "6037-9911-1234-5678", card_holder: "Polymart Store" };

  it("shows the destination card and lets the buyer submit a transfer reference", async () => {
    authed();
    let submitted = false;
    server.use(
      http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order())),
      http.get(`*/payments/for-order/${NUMBER}/`, () =>
        HttpResponse.json(
          codPayment({
            method: "card_to_card",
            status: "pending",
            transfer_reference: submitted ? "TRK-778899" : null,
          }),
        ),
      ),
      http.get(`*/payments/for-order/${NUMBER}/card-to-card/`, () => HttpResponse.json(CARD)),
      http.post(`*/payments/for-order/${NUMBER}/transfer-reference/`, () => {
        submitted = true;
        return HttpResponse.json(
          codPayment({ method: "card_to_card", status: "pending", transfer_reference: "TRK-778899" }),
        );
      }),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    // The server-owned destination card is shown (never entered by the buyer).
    expect(await screen.findByText(CARD.card_number)).toBeInTheDocument();
    expect(screen.getByText(CARD.card_holder)).toBeInTheDocument();

    // The buyer reports their transfer reference.
    await userEvent.type(
      screen.getByLabelText(messages.payment.transferReferencePrompt),
      "TRK-778899",
    );
    await userEvent.click(
      screen.getByRole("button", { name: messages.payment.submitTransfer }),
    );

    // After it lands, the block shows the submitted reference + awaiting-confirmation note.
    expect(
      await screen.findByText(messages.payment.transferAwaitingConfirmation),
    ).toBeInTheDocument();
    expect(screen.getByText("TRK-778899")).toBeInTheDocument();
  });

  it("does not show staff confirm/reject controls to a non-staff buyer", async () => {
    authed();
    server.use(
      http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order())),
      http.get(`*/payments/for-order/${NUMBER}/`, () =>
        HttpResponse.json(
          codPayment({ method: "card_to_card", status: "pending", transfer_reference: "TRK-1" }),
        ),
      ),
      http.get(`*/payments/for-order/${NUMBER}/card-to-card/`, () => HttpResponse.json(CARD)),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    await screen.findByText(messages.payment.transferAwaitingConfirmation);
    expect(
      screen.queryByRole("button", { name: messages.payment.confirmTransfer }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: messages.payment.rejectTransfer }),
    ).not.toBeInTheDocument();
  });

  it("lets staff confirm a card-to-card transfer once a reference is submitted", async () => {
    let confirmed = false;
    staffAuthed(
      codPayment({ method: "card_to_card", status: "pending", transfer_reference: "TRK-1" }),
    );
    server.use(
      http.get(`*/orders/${NUMBER}/`, () =>
        HttpResponse.json(order({ status: confirmed ? "paid" : "pending" })),
      ),
      http.get(`*/payments/for-order/${NUMBER}/`, () =>
        HttpResponse.json(
          codPayment({
            method: "card_to_card",
            status: confirmed ? "captured" : "pending",
            transfer_reference: "TRK-1",
          }),
        ),
      ),
      http.get(`*/payments/for-order/${NUMBER}/card-to-card/`, () => HttpResponse.json(CARD)),
      http.post("*/payments/PAY-ABC123XYZ00/confirm/", () => {
        confirmed = true;
        return HttpResponse.json(
          codPayment({ method: "card_to_card", status: "captured", transfer_reference: "TRK-1" }),
        );
      }),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    const confirm = await screen.findByRole("button", {
      name: messages.payment.confirmTransfer,
    });
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);

    // The staff controls disappear once the payment is captured. (The captured label and the
    // order's "paid" label are the same Persian text, so assert via the control's removal.)
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: messages.payment.confirmTransfer }),
      ).not.toBeInTheDocument(),
    );
    const section = screen
      .getByText(messages.payment.sectionTitle)
      .closest("section") as HTMLElement;
    expect(within(section).getByText(messages.payment.statusCaptured)).toBeInTheDocument();
  });

  it("disables confirm until the buyer has submitted a transfer reference", async () => {
    staffAuthed(
      codPayment({ method: "card_to_card", status: "pending", transfer_reference: null }),
    );
    server.use(
      http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order())),
      http.get(`*/payments/for-order/${NUMBER}/card-to-card/`, () => HttpResponse.json(CARD)),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    expect(
      await screen.findByRole("button", { name: messages.payment.confirmTransfer }),
    ).toBeDisabled();
    // Reject is available even before a reference is reported.
    expect(
      screen.getByRole("button", { name: messages.payment.rejectTransfer }),
    ).toBeEnabled();
  });

  // --- Online awaiting-webhook polling -----------------------------------

  it("shows the awaiting banner for a still-settling online payment", async () => {
    authed();
    server.use(
      http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order())),
      http.get(`*/payments/for-order/${NUMBER}/`, () =>
        HttpResponse.json(codPayment({ method: "online", status: "pending" })),
      ),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    // The redirect landed before the gateway callback settled: the page shows a live
    // "confirming" banner rather than a stale unpaid state.
    expect(await screen.findByTestId("online-awaiting")).toBeInTheDocument();
    expect(screen.getByText(messages.payment.awaitingConfirmation)).toBeInTheDocument();
  });

  it("stops polling and clears the banner once the online payment settles", async () => {
    authed();
    let captured = false;
    server.use(
      http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order())),
      // The first read is pending; once the (async) callback settles it, the poll reads captured.
      http.get(`*/payments/for-order/${NUMBER}/`, () =>
        HttpResponse.json(
          codPayment({ method: "online", status: captured ? "captured" : "pending" }),
        ),
      ),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    await screen.findByTestId("online-awaiting");
    captured = true; // the next poll resolves the payment
    await waitForElementToBeRemoved(() => screen.queryByTestId("online-awaiting"), {
      timeout: 6000,
    });
    const section = screen
      .getByText(messages.payment.sectionTitle)
      .closest("section") as HTMLElement;
    expect(within(section).getByText(messages.payment.statusCaptured)).toBeInTheDocument();
  });

  it("does not show the awaiting banner for a captured online payment", async () => {
    authed();
    server.use(
      http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order({ status: "paid" }))),
      http.get(`*/payments/for-order/${NUMBER}/`, () =>
        HttpResponse.json(codPayment({ method: "online", status: "captured" })),
      ),
    );

    renderWithProviders(<OrderDetail number={NUMBER} />);

    await screen.findByText(messages.payment.statusCaptured);
    expect(screen.queryByTestId("online-awaiting")).not.toBeInTheDocument();
  });

  it("does not poll or show the awaiting banner for a pending COD payment", async () => {
    authed();
    server.use(http.get(`*/orders/${NUMBER}/`, () => HttpResponse.json(order())));

    renderWithProviders(<OrderDetail number={NUMBER} />);

    await screen.findByText(messages.payment.methodCod);
    expect(screen.queryByTestId("online-awaiting")).not.toBeInTheDocument();
  });
});

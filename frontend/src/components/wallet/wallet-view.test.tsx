import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { WalletView } from "@/components/wallet/wallet-view";
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

function walletBody(overrides: Record<string, unknown> = {}) {
  return {
    balance: "240000.0000",
    currency: "IRR",
    transactions: [
      {
        type: "credit",
        amount: "240000.0000",
        currency: "IRR",
        reason: "refund",
        balance_after: "240000.0000",
        source_reference: "PAY-ABC123XYZ00",
        created_at: "2026-07-05T12:00:00Z",
      },
    ],
    ...overrides,
  };
}

describe("WalletView", () => {
  it("renders the server balance in Toman and the statement", async () => {
    markSignedIn();
    server.use(http.get("*/wallet/", () => HttpResponse.json(walletBody())));

    renderWithProviders(<WalletView />);

    // 240000 IRR -> 24,000 Toman (divide by 10); the balance is the server string, not
    // recomputed. Persian digits are used, so assert on the testid element's text content.
    const balance = await screen.findByTestId("wallet-balance");
    expect(balance.textContent).toContain("تومان");
    // The statement lists the refund entry with its localized reason.
    expect(screen.getByText(messages.wallet.reasonRefund)).toBeInTheDocument();
  });

  it("renders a wallet-payment debit entry with its localized reason", async () => {
    markSignedIn();
    server.use(
      http.get("*/wallet/", () =>
        HttpResponse.json(
          walletBody({
            balance: "90000.0000",
            transactions: [
              {
                type: "debit",
                amount: "150000.0000",
                currency: "IRR",
                reason: "order_payment",
                balance_after: "90000.0000",
                source_reference: "PAY-WALLET00001",
                created_at: "2026-07-06T12:00:00Z",
              },
            ],
          }),
        ),
      ),
    );

    renderWithProviders(<WalletView />);

    // The debit is labelled "خرید" (order payment) and shown with a leading minus.
    const reason = await screen.findByText(messages.wallet.reasonOrderPayment);
    expect(reason).toBeInTheDocument();
    const row = reason.closest("tr");
    expect(row?.textContent).toContain("−");
  });

  it("shows an empty state when the wallet has no transactions", async () => {
    markSignedIn();
    server.use(
      http.get("*/wallet/", () =>
        HttpResponse.json(walletBody({ balance: "0", transactions: [] })),
      ),
    );

    renderWithProviders(<WalletView />);

    expect(await screen.findByText(messages.wallet.empty)).toBeInTheDocument();
  });

  it("shows an error when the wallet fails to load", async () => {
    markSignedIn();
    server.use(
      http.get("*/wallet/", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderWithProviders(<WalletView />);

    expect(await screen.findByText("boom")).toBeInTheDocument();
  });
});

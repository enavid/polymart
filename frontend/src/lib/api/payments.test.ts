import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { ApiError } from "@/lib/api/client";
import { getPayment, getPaymentForOrder, initiatePayment } from "@/lib/api/payments";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const codPayment = {
  reference: "PAY-ABC123XYZ00",
  order_number: "ORD-ABC123XYZ0",
  method: "cod",
  amount: "240000.0000",
  currency: "IRR",
  status: "pending",
  created_at: "2026-07-02T12:00:00Z",
};

describe("payments api", () => {
  it("initiates a payment with the order number and method", async () => {
    let body: unknown;
    server.use(
      http.post("*/payments/", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...codPayment, next_action: "none", redirect_url: null }, {
          status: 201,
        });
      }),
    );

    const result = await initiatePayment("ORD-ABC123XYZ0", "cod");

    expect(body).toEqual({ order_number: "ORD-ABC123XYZ0", method: "cod" });
    expect(result.next_action).toBe("none");
    expect(result.redirect_url).toBeNull();
    // Money stays an exact string end to end -- never a float.
    expect(result.amount).toBe("240000.0000");
  });

  it("reads the payment for an order", async () => {
    let seenUrl = "";
    server.use(
      http.get("*/payments/for-order/ORD-ABC123XYZ0/", ({ request }) => {
        seenUrl = request.url;
        return HttpResponse.json(codPayment);
      }),
    );

    const payment = await getPaymentForOrder("ORD-ABC123XYZ0");

    expect(seenUrl).toContain("/payments/for-order/ORD-ABC123XYZ0/");
    expect(payment.method).toBe("cod");
  });

  it("reads a payment by reference", async () => {
    server.use(
      http.get("*/payments/PAY-ABC123XYZ00/", () => HttpResponse.json(codPayment)),
    );

    const payment = await getPayment("PAY-ABC123XYZ00");
    expect(payment.reference).toBe("PAY-ABC123XYZ00");
  });

  it("surfaces a 404 as an ApiError", async () => {
    server.use(
      http.get("*/payments/for-order/ORD-NONE00000000/", () =>
        HttpResponse.json({ detail: "payment not found" }, { status: 404 }),
      ),
    );

    await expect(getPaymentForOrder("ORD-NONE00000000")).rejects.toBeInstanceOf(ApiError);
  });
});

import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import {
  addCartItem,
  getCart,
  removeCartItem,
  updateCartItem,
} from "@/lib/api/cart";
import { ApiError } from "@/lib/api/client";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const cart = {
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

describe("cart api", () => {
  it("reads the cart for a channel", async () => {
    let seenUrl = "";
    server.use(
      http.get("*/cart/", ({ request }) => {
        seenUrl = request.url;
        return HttpResponse.json(cart);
      }),
    );

    const result = await getCart("ir-main");

    expect(result.total).toBe("240000.0000");
    expect(seenUrl).toContain("channel=ir-main");
  });

  it("adds an item", async () => {
    let body: unknown;
    server.use(
      http.post("*/cart/items/", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(cart);
      }),
    );

    const result = await addCartItem({ channel: "ir-main", sku: "HB-250", quantity: 2 });

    expect(result.items[0].sku).toBe("HB-250");
    expect(body).toEqual({ channel: "ir-main", sku: "HB-250", quantity: 2 });
  });

  it("updates an item quantity", async () => {
    let body: unknown;
    server.use(
      http.put("*/cart/items/HB-250/", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(cart);
      }),
    );

    await updateCartItem("HB-250", "ir-main", 5);

    expect(body).toEqual({ channel: "ir-main", quantity: 5 });
  });

  it("removes an item with the channel in the query string", async () => {
    let seenUrl = "";
    server.use(
      http.delete("*/cart/items/HB-250/", ({ request }) => {
        seenUrl = request.url;
        return HttpResponse.json({ ...cart, items: [], total: "0" });
      }),
    );

    const result = await removeCartItem("HB-250", "ir-main");

    expect(result.items).toEqual([]);
    expect(seenUrl).toContain("channel=ir-main");
  });

  it("surfaces a backend error as an ApiError", async () => {
    server.use(
      http.post("*/cart/items/", () =>
        HttpResponse.json({ detail: "unknown variant" }, { status: 404 }),
      ),
    );

    await expect(
      addCartItem({ channel: "ir-main", sku: "GHOST", quantity: 1 }),
    ).rejects.toBeInstanceOf(ApiError);
  });
});

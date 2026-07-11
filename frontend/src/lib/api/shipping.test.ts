import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { listShippingMethods } from "@/lib/api/shipping";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const methods = [
  { code: "standard", name: "پست پیشتاز", price: "50000.0000", currency: "IRR", min_days: 3, max_days: 5 },
  { code: "express", name: "پیک اکسپرس", price: "120000.0000", currency: "IRR", min_days: 1, max_days: 2 },
];

describe("shipping api", () => {
  it("lists a channel's methods and passes the channel as a query param", async () => {
    let seenUrl = "";
    server.use(
      http.get("*/shipping/methods/", ({ request }) => {
        seenUrl = request.url;
        return HttpResponse.json({ channel: "ir-main", methods });
      }),
    );

    const result = await listShippingMethods("ir-main");

    expect(new URL(seenUrl).searchParams.get("channel")).toBe("ir-main");
    expect(result.map((m) => m.code)).toEqual(["standard", "express"]);
    // Price stays the exact server string (never parsed to a float).
    expect(result[0].price).toBe("50000.0000");
  });

  it("returns an empty list for an unconfigured channel", async () => {
    server.use(
      http.get("*/shipping/methods/", () => HttpResponse.json({ channel: "ghost", methods: [] })),
    );

    expect(await listShippingMethods("ghost")).toEqual([]);
  });

  it("passes the destination province/city so the server can resolve the zoned rate", async () => {
    let seenUrl = "";
    server.use(
      http.get("*/shipping/methods/", ({ request }) => {
        seenUrl = request.url;
        return HttpResponse.json({ channel: "ir-main", methods });
      }),
    );

    await listShippingMethods("ir-main", { province: "تهران", city: "تهران" });

    const params = new URL(seenUrl).searchParams;
    expect(params.get("province")).toBe("تهران");
    expect(params.get("city")).toBe("تهران");
  });

  it("omits the destination params when no province is given", async () => {
    let seenUrl = "";
    server.use(
      http.get("*/shipping/methods/", ({ request }) => {
        seenUrl = request.url;
        return HttpResponse.json({ channel: "ir-main", methods });
      }),
    );

    await listShippingMethods("ir-main");

    const params = new URL(seenUrl).searchParams;
    expect(params.has("province")).toBe(false);
    expect(params.has("city")).toBe(false);
  });
});

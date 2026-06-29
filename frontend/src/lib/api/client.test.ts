import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import {
  ApiError,
  apiGet,
  apiPatch,
  apiPost,
  toQuery,
} from "@/lib/api/client";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("api client", () => {
  it("parses a JSON success body", async () => {
    server.use(
      http.get("*/widgets/", () => HttpResponse.json({ id: 7 })),
    );

    await expect(apiGet<{ id: number }>("/widgets/")).resolves.toEqual({ id: 7 });
  });

  it("sends the body and credentials on POST", async () => {
    let sentCredentials: RequestCredentials | undefined;
    let receivedBody: unknown;
    server.use(
      http.post("*/things/", async ({ request }) => {
        sentCredentials = request.credentials;
        receivedBody = await request.json();
        return HttpResponse.json({ ok: true }, { status: 201 });
      }),
    );

    await apiPost("/things/", { name: "a" });

    expect(sentCredentials).toBe("include");
    expect(receivedBody).toEqual({ name: "a" });
  });

  it("returns undefined for an empty 200 body (refresh/grant style)", async () => {
    server.use(http.post("*/grant/", () => new HttpResponse(null, { status: 200 })));

    await expect(apiPost<void>("/grant/")).resolves.toBeUndefined();
  });

  it("throws ApiError carrying the backend detail message", async () => {
    server.use(
      http.post("*/auth/login/", () =>
        HttpResponse.json({ detail: "invalid credentials" }, { status: 401 }),
      ),
    );

    await expect(apiPost("/auth/login/", {})).rejects.toMatchObject({
      status: 401,
      detail: "invalid credentials",
    });
    await expect(apiPost("/auth/login/", {})).rejects.toBeInstanceOf(ApiError);
  });

  it("falls back to a status message when the error body has no detail", async () => {
    server.use(http.get("*/down/", () => new HttpResponse(null, { status: 503 })));

    await expect(apiGet("/down/")).rejects.toMatchObject({
      status: 503,
      detail: "request failed with status 503",
    });
  });

  it("sends PATCH bodies", async () => {
    let receivedBody: unknown;
    server.use(
      http.patch("*/channels/x/", async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json({ is_active: false });
      }),
    );

    await apiPatch("/channels/x/", { is_active: false });

    expect(receivedBody).toEqual({ is_active: false });
  });
});

describe("toQuery", () => {
  it("skips undefined and empty values", () => {
    expect(toQuery({ a: "1", b: undefined, c: "", d: 2 })).toBe("?a=1&d=2");
  });

  it("returns an empty string when nothing is set", () => {
    expect(toQuery({ a: undefined })).toBe("");
  });
});

import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { fetchHealth } from "@/lib/api/health";

const server = setupServer(
  http.get("*/health/", () =>
    HttpResponse.json({
      state: "healthy",
      components: [
        { name: "application", state: "healthy", detail: "" },
        { name: "database", state: "healthy", detail: "" },
      ],
    }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("fetchHealth", () => {
  it("returns the parsed health report", async () => {
    const report = await fetchHealth();

    expect(report.state).toBe("healthy");
    expect(report.components.map((c) => c.name)).toContain("database");
  });

  it("throws on a non-ok response", async () => {
    server.use(
      http.get("*/health/", () => new HttpResponse(null, { status: 503 })),
    );

    await expect(fetchHealth()).rejects.toThrow("API request failed: 503");
  });
});

import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { AdminDashboard } from "@/components/admin/admin-dashboard";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const admin = messages.admin;

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("AdminDashboard", () => {
  it("shows KPI counts from the management read APIs and quick links", async () => {
    server.use(
      http.get("*/catalog/products/", () =>
        HttpResponse.json([
          { code: "a" },
          { code: "b" },
          { code: "c" },
        ]),
      ),
      http.get("*/channels/", () => HttpResponse.json([{ slug: "ir-main" }, { slug: "ir-2" }])),
      http.get("*/access/users/*", () =>
        HttpResponse.json({ count: 7, limit: 1, offset: 0, results: [] }),
      ),
    );

    renderWithProviders(<AdminDashboard />);

    // 3 products, 2 channels, 7 users -> Persian digits.
    expect(await screen.findByText("۳")).toBeInTheDocument();
    expect(screen.getByText("۲")).toBeInTheDocument();
    expect(screen.getByText("۷")).toBeInTheDocument();
    // Quick links into the sections are present.
    expect(screen.getByRole("link", { name: /کاتالوگ/ })).toHaveAttribute(
      "href",
      "/manage/catalog",
    );
    expect(screen.getByText(admin.quickLinks)).toBeInTheDocument();
  });

  it("surfaces a single error banner when a KPI count fails to load", async () => {
    server.use(
      http.get("*/catalog/products/", () => HttpResponse.json([{ code: "a" }])),
      http.get("*/channels/", () => new HttpResponse(null, { status: 500 })),
      http.get("*/access/users/*", () =>
        HttpResponse.json({ count: 1, limit: 1, offset: 0, results: [] }),
      ),
    );

    renderWithProviders(<AdminDashboard />);

    // The failed channels count raises the banner instead of sitting on a silent dash.
    expect(await screen.findByText(admin.kpiLoadError)).toBeInTheDocument();
  });
});

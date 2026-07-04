import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { SiteHeader } from "@/components/layout/site-header";
import { markSignedIn } from "@/lib/auth/session-hint";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const nav = messages.nav;

vi.mock("next/navigation", () => ({
  usePathname: () => "/products",
}));

function me(isStaff: boolean) {
  return http.get("*/auth/me/", () =>
    HttpResponse.json({
      id: 1,
      phone_number: "+989123456789",
      email: "",
      full_name: "Staff",
      is_staff: isStaff,
    }),
  );
}

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  window.localStorage.clear();
});
afterAll(() => server.close());

describe("SiteHeader", () => {
  it("shows a visible management link to staff without opening any menu", async () => {
    markSignedIn();
    server.use(me(true));

    renderWithProviders(<SiteHeader />);

    // The management entry is a top-level, directly-visible link (not inside the
    // account dropdown), so a signed-in staff member sees it at a glance.
    const link = await screen.findByRole("link", { name: nav.admin });
    expect(link).toHaveAttribute("href", "/manage");
  });

  it("does not show the management link to a non-staff shopper", async () => {
    markSignedIn();
    server.use(me(false));

    renderWithProviders(<SiteHeader />);

    // Wait for the session to resolve (the account trigger appears), then assert the
    // management link is absent for a shopper.
    await screen.findByRole("button", { name: /Staff/ });
    expect(screen.queryByRole("link", { name: nav.admin })).not.toBeInTheDocument();
  });
});

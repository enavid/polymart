import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { AdminShell } from "@/components/admin/admin-shell";
import { markSignedIn } from "@/lib/auth/session-hint";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

vi.mock("next/navigation", () => ({ usePathname: () => "/manage" }));

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  window.localStorage.clear();
});
afterAll(() => server.close());

describe("AdminShell", () => {
  it("renders its own sidebar nav, a back-to-store link, and the page content", async () => {
    markSignedIn();
    server.use(
      http.get("*/auth/me/", () =>
        HttpResponse.json({
          id: 1,
          phone_number: "+989123456789",
          email: "",
          full_name: "Staff",
          is_staff: true,
        }),
      ),
    );

    renderWithProviders(
      <AdminShell>
        <div>SECTION CONTENT</div>
      </AdminShell>,
    );

    // Page content is rendered inside the shell.
    expect(screen.getByText("SECTION CONTENT")).toBeInTheDocument();
    // The admin nav exposes the management sections (sidebar + mobile => >= 1 each).
    expect(screen.getAllByRole("link", { name: messages.nav.channels }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: messages.admin.dashboard }).length).toBeGreaterThan(
      0,
    );
    // Its own top bar has a back-to-store escape hatch (not the shopper header).
    expect(
      screen.getByRole("link", { name: messages.admin.backToStore }),
    ).toHaveAttribute("href", "/");
  });
});

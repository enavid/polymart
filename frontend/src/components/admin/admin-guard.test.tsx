import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { AdminGuard } from "@/components/admin/admin-guard";
import { markSignedIn } from "@/lib/auth/session-hint";
import { renderWithProviders } from "@/test/utils";

// Admins sign in through the same login as any customer; the admin area is simply
// hidden (a redirect) from anyone without staff access -- never a "denied" wall.
const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
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
  replace.mockReset();
  window.localStorage.clear();
});
afterAll(() => server.close());

describe("AdminGuard", () => {
  it("renders the admin content for a staff user without redirecting", async () => {
    markSignedIn();
    server.use(me(true));

    renderWithProviders(
      <AdminGuard>
        <div>PANEL</div>
      </AdminGuard>,
    );

    expect(await screen.findByText("PANEL")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("sends a signed-in non-staff user home instead of showing the panel", async () => {
    markSignedIn();
    server.use(me(false));

    renderWithProviders(
      <AdminGuard>
        <div>PANEL</div>
      </AdminGuard>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(screen.queryByText("PANEL")).not.toBeInTheDocument();
  });

  it("sends an anonymous visitor to the shared login with a return path", async () => {
    // No session hint and no /auth/me handler: an unhandled request would fail the
    // test, proving the guard makes no probe and just redirects to the unified login.
    renderWithProviders(
      <AdminGuard>
        <div>PANEL</div>
      </AdminGuard>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=/manage"));
    expect(screen.queryByText("PANEL")).not.toBeInTheDocument();
  });
});

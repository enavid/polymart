import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { AdminGuard } from "@/components/admin/admin-guard";
import { markSignedIn } from "@/lib/auth/session-hint";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const admin = messages.admin;

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

describe("AdminGuard", () => {
  it("renders the admin content for a staff user", async () => {
    markSignedIn();
    server.use(me(true));

    renderWithProviders(
      <AdminGuard>
        <div>PANEL</div>
      </AdminGuard>,
    );

    expect(await screen.findByText("PANEL")).toBeInTheDocument();
  });

  it("shows a forbidden page (not the panel) for a signed-in non-staff user", async () => {
    markSignedIn();
    server.use(me(false));

    renderWithProviders(
      <AdminGuard>
        <div>PANEL</div>
      </AdminGuard>,
    );

    expect(await screen.findByText(admin.guardForbidden)).toBeInTheDocument();
    expect(screen.queryByText("PANEL")).not.toBeInTheDocument();
  });

  it("shows a sign-in prompt (never the panel) for an anonymous visitor", async () => {
    // No session hint and no /auth/me handler: an unhandled request would fail the
    // test, proving the guard makes no probe and just prompts to sign in.
    renderWithProviders(
      <AdminGuard>
        <div>PANEL</div>
      </AdminGuard>,
    );

    expect(await screen.findByText(admin.guardSignIn)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: admin.guardSignInCta })).toHaveAttribute(
      "href",
      "/login?next=/admin",
    );
    expect(screen.queryByText("PANEL")).not.toBeInTheDocument();
  });
});

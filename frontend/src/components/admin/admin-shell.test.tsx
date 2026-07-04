import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { AdminShell } from "@/components/admin/admin-shell";
import { markSignedIn } from "@/lib/auth/session-hint";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

let pathname = "/manage";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

function staff() {
  return http.get("*/auth/me/", () =>
    HttpResponse.json({
      id: 1,
      phone_number: "+989123456789",
      email: "",
      full_name: "Staff",
      is_staff: true,
    }),
  );
}

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  window.localStorage.clear();
  pathname = "/manage";
});
afterAll(() => server.close());

describe("AdminShell", () => {
  it("renders its own sidebar nav, a back-to-store link, and the page content", async () => {
    markSignedIn();
    server.use(staff());

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
    // The nav is grouped into sections, not one flat list.
    expect(screen.getByText(messages.admin.navGroupSystem)).toBeInTheDocument();
  });

  it("exposes the catalog subsections and marks the active one on a nested page", async () => {
    pathname = "/manage/catalog/products/aprl-00";
    markSignedIn();
    server.use(staff());

    renderWithProviders(
      <AdminShell>
        <div>SECTION CONTENT</div>
      </AdminShell>,
    );

    // The catalog subsections live in the sidebar; a product detail page keeps the
    // Products subsection active and no sibling subsection lit.
    const productLinks = screen.getAllByRole("link", { name: messages.catalog.navProducts });
    expect(productLinks.some((link) => link.getAttribute("aria-current") === "page")).toBe(true);
    const typeLinks = screen.getAllByRole("link", { name: messages.catalog.navProductTypes });
    expect(typeLinks.every((link) => link.getAttribute("aria-current") !== "page")).toBe(true);

    // The top bar's section name becomes a back link to the section itself.
    const topBar = screen.getByRole("banner");
    expect(
      within(topBar).getByRole("link", { name: messages.catalog.navProducts }),
    ).toHaveAttribute("href", "/manage/catalog/products");
  });

  it("shows the section name as plain text (not a back link) on the section root", async () => {
    pathname = "/manage/catalog/products";
    markSignedIn();
    server.use(staff());

    renderWithProviders(
      <AdminShell>
        <div>SECTION CONTENT</div>
      </AdminShell>,
    );

    await screen.findAllByRole("link", { name: messages.catalog.navProducts });
    // On the section root the top bar shows the name as text, not a back link.
    const topBar = screen.getByRole("banner");
    expect(
      within(topBar).queryByRole("link", { name: messages.catalog.navProducts }),
    ).not.toBeInTheDocument();
  });

  it("collapses a sidebar section when its heading is clicked", async () => {
    markSignedIn();
    server.use(staff());
    const user = userEvent.setup();

    renderWithProviders(
      <AdminShell>
        <div>SECTION CONTENT</div>
      </AdminShell>,
    );

    await screen.findByRole("link", { name: messages.admin.backToStore });
    // Channels shows in both the sidebar and the mobile nav while expanded.
    expect(screen.getAllByRole("link", { name: messages.nav.channels })).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: messages.admin.navGroupSystem }));

    // Collapsing the System section removes its sidebar links; the mobile nav copy stays.
    expect(screen.getAllByRole("link", { name: messages.nav.channels })).toHaveLength(1);
  });

  it("collapses the whole sidebar to an icon rail and back", async () => {
    markSignedIn();
    server.use(staff());
    const user = userEvent.setup();

    renderWithProviders(
      <AdminShell>
        <div>SECTION CONTENT</div>
      </AdminShell>,
    );

    // Expanded: the group headings are visible.
    await screen.findByText(messages.admin.navGroupSystem);

    // Collapsing to the rail drops the group headings but keeps every section
    // reachable (icon links carry the label as their accessible name).
    await user.click(screen.getByRole("button", { name: messages.admin.collapseMenu }));
    expect(screen.queryByText(messages.admin.navGroupSystem)).not.toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: messages.nav.channels }).length,
    ).toBeGreaterThan(0);

    // Expanding restores the headings.
    await user.click(screen.getByRole("button", { name: messages.admin.expandMenu }));
    expect(screen.getByText(messages.admin.navGroupSystem)).toBeInTheDocument();
  });
});

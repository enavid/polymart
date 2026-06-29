import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { AccessPanel } from "@/components/admin/access-panel";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("AccessPanel", () => {
  it("notes that user create/list is not part of the Phase 1 API", () => {
    renderWithProviders(<AccessPanel />);
    expect(screen.getByText(messages.admin.userManagementNote)).toBeInTheDocument();
  });

  it("assigns a role and shows success", async () => {
    let body: unknown;
    server.use(
      http.post("*/access/role-assignments/", async ({ request }) => {
        body = await request.json();
        return new HttpResponse(null, { status: 200 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccessPanel />);

    // Two userId fields exist (role form + grant form); the first is the role form.
    const userIdFields = screen.getAllByLabelText(messages.admin.userId);
    await user.type(userIdFields[0], "5");
    await user.type(screen.getByLabelText(messages.admin.role), "catalog_admin");
    await user.click(
      screen.getByRole("button", { name: messages.admin.assignRoleCta }),
    );

    expect(
      await screen.findByText(messages.admin.assignRoleSuccess),
    ).toBeInTheDocument();
    expect(body).toEqual({ user_id: 5, role: "catalog_admin" });
  });

  it("shows the forbidden message when the caller lacks manage_access (403)", async () => {
    server.use(
      http.post("*/access/role-assignments/", () =>
        HttpResponse.json({ detail: "no" }, { status: 403 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccessPanel />);
    const userIdFields = screen.getAllByLabelText(messages.admin.userId);
    await user.type(userIdFields[0], "5");
    await user.type(screen.getByLabelText(messages.admin.role), "x");
    await user.click(
      screen.getByRole("button", { name: messages.admin.assignRoleCta }),
    );

    expect(await screen.findByText(messages.admin.forbidden)).toBeInTheDocument();
  });

  it("grants channel management to a user", async () => {
    let body: unknown;
    server.use(
      http.post("*/access/channel-grants/", async ({ request }) => {
        body = await request.json();
        return new HttpResponse(null, { status: 200 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccessPanel />);
    const userIdFields = screen.getAllByLabelText(messages.admin.userId);
    await user.type(userIdFields[1], "7");
    await user.type(screen.getByLabelText(messages.admin.channelSlug), "coffee-ir");
    await user.click(
      screen.getByRole("button", { name: messages.admin.grantChannelCta }),
    );

    expect(
      await screen.findByText(messages.admin.grantChannelSuccess),
    ).toBeInTheDocument();
    expect(body).toEqual({ user_id: 7, channel_slug: "coffee-ir" });
  });
});

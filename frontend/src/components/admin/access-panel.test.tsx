import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { AccessPanel } from "@/components/admin/access-panel";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const USERS = [
  {
    id: 5,
    phone_number: "+989120000005",
    full_name: "Ali",
    email: "",
    is_staff: false,
    is_active: true,
  },
  {
    id: 7,
    phone_number: "+989120000007",
    full_name: "Sara",
    email: "",
    is_staff: true,
    is_active: true,
  },
];

function usersHandler() {
  return http.get("*/access/users/", () =>
    HttpResponse.json({ count: USERS.length, limit: 100, offset: 0, results: USERS }),
  );
}

const server = setupServer(usersHandler());
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers(usersHandler()));
afterAll(() => server.close());

describe("AccessPanel", () => {
  it("lists the users fetched from the access API", async () => {
    renderWithProviders(<AccessPanel />);

    // "Ali" appears in the list and in both user pickers, so there are several.
    expect((await screen.findAllByText(/Ali/)).length).toBeGreaterThan(0);
    // The staff user carries a staff badge (unique to the list).
    expect(screen.getByText(messages.admin.staffBadge)).toBeInTheDocument();
  });

  it("assigns a role to the picked user and shows success", async () => {
    let body: unknown;
    server.use(
      http.post("*/access/role-assignments/", async ({ request }) => {
        body = await request.json();
        return new HttpResponse(null, { status: 200 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccessPanel />);
    await screen.findByText(messages.admin.staffBadge);

    // Two user pickers exist (role form + grant form); the first is the role form.
    const pickers = screen.getAllByLabelText(messages.admin.selectUser);
    await user.selectOptions(pickers[0], "5");
    await user.type(screen.getByLabelText(messages.admin.role), "catalog_admin");
    await user.click(screen.getByRole("button", { name: messages.admin.assignRoleCta }));

    expect(await screen.findByText(messages.admin.assignRoleSuccess)).toBeInTheDocument();
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
    await screen.findByText(messages.admin.staffBadge);

    const pickers = screen.getAllByLabelText(messages.admin.selectUser);
    await user.selectOptions(pickers[0], "5");
    await user.type(screen.getByLabelText(messages.admin.role), "x");
    await user.click(screen.getByRole("button", { name: messages.admin.assignRoleCta }));

    expect(await screen.findByText(messages.admin.forbidden)).toBeInTheDocument();
  });

  it("grants channel management to the picked user", async () => {
    let body: unknown;
    server.use(
      http.post("*/access/channel-grants/", async ({ request }) => {
        body = await request.json();
        return new HttpResponse(null, { status: 200 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccessPanel />);
    await screen.findByText(messages.admin.staffBadge);

    const pickers = screen.getAllByLabelText(messages.admin.selectUser);
    await user.selectOptions(pickers[1], "7");
    await user.type(screen.getByLabelText(messages.admin.channelSlug), "coffee-ir");
    await user.click(screen.getByRole("button", { name: messages.admin.grantChannelCta }));

    expect(await screen.findByText(messages.admin.grantChannelSuccess)).toBeInTheDocument();
    expect(body).toEqual({ user_id: 7, channel_slug: "coffee-ir" });
  });

  it("creates a user and sends the entered fields", async () => {
    let body: unknown;
    server.use(
      http.post("*/access/users/", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          {
            id: 9,
            phone_number: "+989121112233",
            full_name: "New Person",
            email: "",
            is_staff: true,
            is_active: true,
          },
          { status: 201 },
        );
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccessPanel />);
    await screen.findByText(messages.admin.staffBadge);

    await user.type(screen.getByLabelText(messages.common.phoneNumber), "09121112233");
    await user.type(screen.getByLabelText(messages.common.password), "s3cret-pw");
    await user.type(screen.getByLabelText(messages.admin.fullName), "New Person");
    await user.click(screen.getByLabelText(messages.admin.isStaff));
    await user.click(screen.getByRole("button", { name: messages.admin.createUserCta }));

    expect(await screen.findByText(messages.admin.createUserSuccess)).toBeInTheDocument();
    expect(body).toEqual({
      phone_number: "09121112233",
      password: "s3cret-pw",
      full_name: "New Person",
      is_staff: true,
    });
  });

  it("shows a duplicate-user message on 409", async () => {
    server.use(
      http.post("*/access/users/", () =>
        HttpResponse.json({ detail: "exists" }, { status: 409 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccessPanel />);
    await screen.findByText(messages.admin.staffBadge);

    await user.type(screen.getByLabelText(messages.common.phoneNumber), "09121112233");
    await user.type(screen.getByLabelText(messages.common.password), "pw");
    await user.click(screen.getByRole("button", { name: messages.admin.createUserCta }));

    expect(await screen.findByText(messages.admin.userExists)).toBeInTheDocument();
  });

  it("refetches the user list after a successful create", async () => {
    let getCalls = 0;
    server.use(
      http.get("*/access/users/", () => {
        getCalls += 1;
        return HttpResponse.json({ count: USERS.length, limit: 100, offset: 0, results: USERS });
      }),
      http.post("*/access/users/", () =>
        HttpResponse.json(
          {
            id: 9,
            phone_number: "+989121112233",
            full_name: "New Person",
            email: "",
            is_staff: false,
            is_active: true,
          },
          { status: 201 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccessPanel />);
    await screen.findByText(messages.admin.staffBadge);
    const initialCalls = getCalls;

    await user.type(screen.getByLabelText(messages.common.phoneNumber), "09121112233");
    await user.type(screen.getByLabelText(messages.common.password), "pw");
    await user.click(screen.getByRole("button", { name: messages.admin.createUserCta }));

    await screen.findByText(messages.admin.createUserSuccess);
    await waitFor(() => expect(getCalls).toBeGreaterThan(initialCalls));
  });
});

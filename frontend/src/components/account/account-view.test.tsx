import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { AccountView } from "@/components/account/account-view";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("AccountView", () => {
  it("renders the signed-in user's profile", async () => {
    server.use(
      http.get("*/auth/me/", () =>
        HttpResponse.json({
          id: 1,
          phone_number: "+989123456789",
          email: "a@example.com",
          full_name: "Ali Rezaei",
          is_staff: true,
        }),
      ),
    );

    renderWithProviders(<AccountView />);

    expect(await screen.findByText("+989123456789")).toBeInTheDocument();
    expect(screen.getByText("Ali Rezaei")).toBeInTheDocument();
    expect(screen.getByText(messages.account.yes)).toBeInTheDocument();
  });

  it("prompts to log in when unauthenticated (401)", async () => {
    server.use(
      http.get("*/auth/me/", () =>
        HttpResponse.json({ detail: "no" }, { status: 401 }),
      ),
    );

    renderWithProviders(<AccountView />);

    expect(
      await screen.findByText(messages.account.notLoggedIn),
    ).toBeInTheDocument();
  });

  it("logs out and returns to the unauthenticated state", async () => {
    server.use(
      http.get("*/auth/me/", () =>
        HttpResponse.json({
          id: 1,
          phone_number: "+989123456789",
          email: "",
          full_name: "Ali",
          is_staff: false,
        }),
      ),
      http.post("*/auth/logout/", () => new HttpResponse(null, { status: 200 })),
    );

    const user = userEvent.setup();
    renderWithProviders(<AccountView />);

    await screen.findByText("+989123456789");
    await user.click(screen.getByRole("button", { name: messages.nav.logout }));

    await waitFor(() =>
      expect(screen.getByText(messages.account.notLoggedIn)).toBeInTheDocument(),
    );
  });
});

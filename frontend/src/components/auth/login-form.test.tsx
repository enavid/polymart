import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { LoginForm } from "@/components/auth/login-form";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  push.mockReset();
});
afterAll(() => server.close());

async function fillAndSubmit() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(messages.common.phoneNumber), "09123456789");
  await user.type(screen.getByLabelText(messages.common.password), "secret123");
  await user.click(screen.getByRole("button", { name: messages.auth.loginCta }));
}

describe("LoginForm", () => {
  it("logs in and redirects to the account page on success", async () => {
    server.use(
      http.post("*/auth/login/", () =>
        HttpResponse.json({
          id: 1,
          phone_number: "+989123456789",
          email: "",
          full_name: "Ali",
          is_staff: false,
        }),
      ),
    );

    renderWithProviders(<LoginForm />);
    await fillAndSubmit();

    await waitFor(() => expect(push).toHaveBeenCalledWith("/account"));
  });

  it("shows the uniform invalid-credentials message on 401", async () => {
    server.use(
      http.post("*/auth/login/", () =>
        HttpResponse.json({ detail: "invalid credentials" }, { status: 401 }),
      ),
    );

    renderWithProviders(<LoginForm />);
    await fillAndSubmit();

    expect(
      await screen.findByText(messages.auth.invalidCredentials),
    ).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("cannot leak credentials into a URL if the client never hydrates", async () => {
    // A native fallback submit must be a POST (body, not query string) and the
    // credential fields must carry no name, so the password can never be
    // serialized into a URL / browser history / server log.
    const { container } = renderWithProviders(<LoginForm />);

    const form = container.querySelector("form");
    expect(form).not.toBeNull();
    expect(form?.getAttribute("method")).toBe("post");

    expect(screen.getByLabelText(messages.common.password)).not.toHaveAttribute("name");
    expect(screen.getByLabelText(messages.common.phoneNumber)).not.toHaveAttribute("name");
  });

  it("surfaces the error detail on an unexpected server error", async () => {
    server.use(
      http.post("*/auth/login/", () => new HttpResponse(null, { status: 500 })),
    );

    renderWithProviders(<LoginForm />);
    await fillAndSubmit();

    expect(
      await screen.findByText(/request failed with status 500/),
    ).toBeInTheDocument();
  });
});

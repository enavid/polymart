import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { RegisterForm } from "@/components/auth/register-form";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("RegisterForm", () => {
  it("requests an OTP for the registration purpose", async () => {
    let purpose: unknown;
    server.use(
      http.post("*/auth/otp/request/", async ({ request }) => {
        purpose = ((await request.json()) as { purpose: string }).purpose;
        return HttpResponse.json({ detail: "sent" }, { status: 202 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<RegisterForm />);
    await user.type(
      screen.getByLabelText(messages.common.phoneNumber),
      "09123456789",
    );
    await user.click(screen.getByRole("button", { name: messages.auth.otpCta }));

    await waitFor(() => expect(purpose).toBe("registration"));
    expect(await screen.findByText(messages.auth.otpSent)).toBeInTheDocument();
  });

  it("shows a success panel after creating the account", async () => {
    server.use(
      http.post("*/auth/register/", () =>
        HttpResponse.json(
          {
            id: 2,
            phone_number: "+989123456789",
            email: "",
            full_name: "",
            is_staff: false,
          },
          { status: 201 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<RegisterForm />);
    await user.type(
      screen.getByLabelText(messages.common.phoneNumber),
      "09123456789",
    );
    await user.type(screen.getByLabelText(messages.auth.code), "123456");
    await user.type(screen.getByLabelText(messages.common.password), "secret123");
    await user.click(
      screen.getByRole("button", { name: messages.auth.registerCta }),
    );

    expect(
      await screen.findByText(messages.auth.registerSuccess),
    ).toBeInTheDocument();
  });

  it("surfaces the backend detail when the code is invalid", async () => {
    server.use(
      http.post("*/auth/register/", () =>
        HttpResponse.json(
          { detail: "invalid verification code" },
          { status: 400 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<RegisterForm />);
    await user.type(
      screen.getByLabelText(messages.common.phoneNumber),
      "09123456789",
    );
    await user.type(screen.getByLabelText(messages.auth.code), "000000");
    await user.type(screen.getByLabelText(messages.common.password), "secret123");
    await user.click(
      screen.getByRole("button", { name: messages.auth.registerCta }),
    );

    expect(
      await screen.findByText("invalid verification code"),
    ).toBeInTheDocument();
  });
});

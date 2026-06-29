import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { PasswordResetForm } from "@/components/auth/password-reset-form";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

async function fill() {
  const user = userEvent.setup();
  await user.type(
    screen.getByLabelText(messages.common.phoneNumber),
    "09123456789",
  );
  await user.type(screen.getByLabelText(messages.auth.code), "123456");
  await user.type(
    screen.getByLabelText(messages.auth.newPassword),
    "newsecret1",
  );
  await user.click(screen.getByRole("button", { name: messages.auth.resetCta }));
}

describe("PasswordResetForm", () => {
  it("shows the uniform done message on success", async () => {
    server.use(
      http.post("*/auth/password-reset/", () =>
        HttpResponse.json({ detail: "ok" }),
      ),
    );

    renderWithProviders(<PasswordResetForm />);
    await fill();

    expect(await screen.findByText(messages.auth.resetDone)).toBeInTheDocument();
  });

  it("surfaces the backend detail on an expired code", async () => {
    server.use(
      http.post("*/auth/password-reset/", () =>
        HttpResponse.json(
          { detail: "the verification code has expired" },
          { status: 400 },
        ),
      ),
    );

    renderWithProviders(<PasswordResetForm />);
    await fill();

    expect(
      await screen.findByText("the verification code has expired"),
    ).toBeInTheDocument();
  });
});

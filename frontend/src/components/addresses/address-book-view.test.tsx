import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { AddressBookView } from "@/components/addresses/address-book-view";
import { markSignedIn } from "@/lib/auth/session-hint";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  window.localStorage.clear();
});
afterAll(() => server.close());

function authed() {
  markSignedIn();
  server.use(
    http.get("*/auth/me/", () =>
      HttpResponse.json({
        id: 7,
        phone_number: "+989120000001",
        email: "",
        full_name: "Shopper",
        is_staff: false,
      }),
    ),
  );
}

const addressA = {
  id: "ADDR-FIRST0001",
  recipient_name: "Sara Ahmadi",
  phone_number: "+989123456789",
  province: "Tehran",
  city: "Tehran",
  postal_code: "1234567890",
  line1: "Valiasr St, No. 1",
  line2: null,
  is_default: true,
  created_at: "2026-07-02T12:00:00Z",
};

const addressB = {
  ...addressA,
  id: "ADDR-SECOND002",
  recipient_name: "Reza Karimi",
  city: "Shiraz",
  is_default: false,
};

const FIELD_LABELS: Record<string, string> = {
  recipient_name: messages.addresses.recipientName,
  phone_number: messages.addresses.phoneNumber,
  province: messages.addresses.province,
  city: messages.addresses.city,
  postal_code: messages.addresses.postalCode,
  line1: messages.addresses.line1,
};

/** Clear and retype every required field of the (already-open) address form. */
async function fillForm(overrides: Record<string, string> = {}) {
  const values: Record<string, string> = {
    recipient_name: "Sara Ahmadi",
    phone_number: "09123456789",
    province: "Tehran",
    city: "Tehran",
    postal_code: "1234567890",
    line1: "Valiasr St, No. 1",
    ...overrides,
  };
  for (const [field, label] of Object.entries(FIELD_LABELS)) {
    const input = screen.getByLabelText(label);
    await userEvent.clear(input);
    await userEvent.type(input, values[field]);
  }
}

describe("AddressBookView", () => {
  it("prompts to log in when unauthenticated", async () => {
    server.use(
      http.get("*/auth/me/", () => HttpResponse.json({ detail: "no" }, { status: 401 })),
    );

    renderWithProviders(<AddressBookView />);

    expect(await screen.findByText(messages.addresses.loginRequired)).toBeInTheDocument();
  });

  it("shows an empty address book", async () => {
    authed();
    server.use(http.get("*/addresses/", () => HttpResponse.json([])));

    renderWithProviders(<AddressBookView />);

    expect(await screen.findByText(messages.addresses.empty)).toBeInTheDocument();
  });

  it("lists addresses with the default one marked", async () => {
    authed();
    server.use(http.get("*/addresses/", () => HttpResponse.json([addressA, addressB])));

    renderWithProviders(<AddressBookView />);

    expect(await screen.findByText("Sara Ahmadi")).toBeInTheDocument();
    expect(screen.getByText("Reza Karimi")).toBeInTheDocument();
    expect(screen.getAllByText(messages.addresses.default)).toHaveLength(1);
    expect(screen.getAllByText("Valiasr St, No. 1")).toHaveLength(2);
  });

  it("surfaces a load error", async () => {
    authed();
    server.use(
      http.get("*/addresses/", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );

    renderWithProviders(<AddressBookView />);

    expect(await screen.findByText("boom")).toBeInTheDocument();
  });

  it("creates a new address and returns to the list", async () => {
    authed();
    let created: Record<string, unknown> | null = null;
    server.use(
      http.get("*/addresses/", () => HttpResponse.json(created ? [created] : [])),
      http.post("*/addresses/", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        created = { ...addressA, ...body, id: "ADDR-NEW00001", is_default: true };
        return HttpResponse.json(created, { status: 201 });
      }),
    );

    renderWithProviders(<AddressBookView />);
    const addButton = await screen.findByRole("button", { name: messages.addresses.addNew });
    await userEvent.click(addButton);

    await fillForm();
    await userEvent.click(screen.getByRole("button", { name: messages.addresses.save }));

    await waitFor(() => expect(screen.getByText("Sara Ahmadi")).toBeInTheDocument());
    // The form closes back to the list view.
    expect(screen.queryByRole("button", { name: messages.addresses.save })).not.toBeInTheDocument();
  });

  it("shows a validation error on a rejected create without navigating away", async () => {
    authed();
    server.use(
      http.get("*/addresses/", () => HttpResponse.json([])),
      http.post("*/addresses/", () => HttpResponse.json({ detail: "12345" }, { status: 400 })),
    );

    renderWithProviders(<AddressBookView />);
    await userEvent.click(
      await screen.findByRole("button", { name: messages.addresses.addNew }),
    );
    await fillForm({ postal_code: "123" });
    await userEvent.click(screen.getByRole("button", { name: messages.addresses.save }));

    // The raw backend detail is not shopper-appropriate; a localized message is shown.
    expect(await screen.findByText(messages.addresses.validationError)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: messages.addresses.save })).toBeInTheDocument();
  });

  it("shows the limit-exceeded message on a 409", async () => {
    authed();
    server.use(
      http.get("*/addresses/", () => HttpResponse.json([addressA])),
      http.post("*/addresses/", () => HttpResponse.json({ detail: "limit" }, { status: 409 })),
    );

    renderWithProviders(<AddressBookView />);
    await userEvent.click(
      await screen.findByRole("button", { name: messages.addresses.addNew }),
    );
    await fillForm();
    await userEvent.click(screen.getByRole("button", { name: messages.addresses.save }));

    expect(await screen.findByText(messages.addresses.limitExceeded)).toBeInTheDocument();
  });

  it("edits an address without changing its default status", async () => {
    authed();
    let current = { ...addressA };
    server.use(
      http.get("*/addresses/", () => HttpResponse.json([current])),
      http.put("*/addresses/:id", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        current = { ...current, ...body, city: "Shiraz" };
        return HttpResponse.json(current);
      }),
    );

    renderWithProviders(<AddressBookView />);
    await userEvent.click(await screen.findByRole("button", { name: messages.addresses.edit }));

    // Prefilled from the existing address.
    expect(screen.getByLabelText(messages.addresses.recipientName)).toHaveValue("Sara Ahmadi");
    await userEvent.click(screen.getByRole("button", { name: messages.addresses.save }));

    await waitFor(() => expect(screen.getByText("Tehran، Shiraz")).toBeInTheDocument());
    expect(screen.getByText(messages.addresses.default)).toBeInTheDocument();
  });

  it("deletes an address after inline confirmation", async () => {
    authed();
    let deleted = false;
    server.use(
      http.get("*/addresses/", () => HttpResponse.json(deleted ? [] : [addressA])),
      http.delete("*/addresses/:id", () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderWithProviders(<AddressBookView />);
    const deleteButtons = await screen.findAllByRole("button", { name: messages.addresses.delete });
    await userEvent.click(deleteButtons[0]);

    // Confirmation text appears; the delete has not happened yet (no browser dialog).
    expect(screen.getByText(messages.addresses.deleteConfirm)).toBeInTheDocument();
    const confirmButtons = screen.getAllByRole("button", { name: messages.addresses.delete });
    await userEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => expect(screen.getByText(messages.addresses.empty)).toBeInTheDocument());
  });

  it("cancels a pending delete without calling the API", async () => {
    authed();
    server.use(http.get("*/addresses/", () => HttpResponse.json([addressA])));

    renderWithProviders(<AddressBookView />);
    await userEvent.click(
      await screen.findByRole("button", { name: messages.addresses.delete }),
    );
    expect(screen.getByText(messages.addresses.deleteConfirm)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: messages.addresses.cancel }));

    expect(screen.queryByText(messages.addresses.deleteConfirm)).not.toBeInTheDocument();
    expect(screen.getByText("Sara Ahmadi")).toBeInTheDocument();
  });

  it("sets a non-default address as the default", async () => {
    authed();
    let addresses = [addressA, addressB];
    server.use(
      http.get("*/addresses/", () => HttpResponse.json(addresses)),
      http.post("*/addresses/:id/default/", ({ params }) => {
        addresses = addresses.map((a) => ({ ...a, is_default: a.id === params.id }));
        const updated = addresses.find((a) => a.id === params.id)!;
        return HttpResponse.json(updated);
      }),
    );

    renderWithProviders(<AddressBookView />);
    await screen.findByText("Sara Ahmadi");
    // Reza Karimi (addressB) is not the default yet, so its card has the button.
    const setDefaultButton = screen.getByRole("button", { name: messages.addresses.setDefault });
    await userEvent.click(setDefaultButton);

    // The default badge now sits on Reza Karimi's card, not Sara Ahmadi's, and
    // exactly one address is ever marked default.
    await waitFor(() => {
      const card = screen.getByText("Reza Karimi").closest("div")!;
      expect(within(card).getByText(messages.addresses.default)).toBeInTheDocument();
    });
    expect(screen.getAllByText(messages.addresses.default)).toHaveLength(1);
  });

  it("does not show protected data to a logged-out user even after a slow response", async () => {
    server.use(
      http.get("*/auth/me/", () => HttpResponse.json({ detail: "no" }, { status: 401 })),
      http.get("*/addresses/", () => HttpResponse.json([addressA])),
    );

    renderWithProviders(<AddressBookView />);

    expect(await screen.findByText(messages.addresses.loginRequired)).toBeInTheDocument();
    expect(screen.queryByText("Sara Ahmadi")).not.toBeInTheDocument();
  });
});

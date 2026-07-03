import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { ManualOrderForm } from "@/components/admin/orders/manual-order-form";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const manual = messages.manualOrder;
const addr = messages.addresses;

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  push.mockReset();
});
afterAll(() => server.close());

async function fillAddress() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(addr.recipientName), "Sara Ahmadi");
  await user.type(screen.getByLabelText(addr.phoneNumber), "09123456789");
  await user.type(screen.getByLabelText(addr.province), "Tehran");
  await user.type(screen.getByLabelText(addr.city), "Tehran");
  await user.type(screen.getByLabelText(addr.postalCode), "1234567890");
  await user.type(screen.getByLabelText(addr.line1), "Valiasr St");
  return user;
}

describe("ManualOrderForm", () => {
  it("submits the channel, lines and inline address, then navigates to the pre-invoice", async () => {
    let captured: unknown = null;
    server.use(
      http.post("*/orders/manual/", async ({ request }) => {
        captured = await request.json();
        return HttpResponse.json({ number: "ORD-MANUAL01" }, { status: 201 });
      }),
    );

    renderWithProviders(<ManualOrderForm />);
    const user = await fillAddress();
    await user.type(screen.getByLabelText(manual.sku), "HB-250");
    const qty = screen.getByLabelText(manual.quantity);
    await user.clear(qty);
    await user.type(qty, "2");
    await user.click(screen.getByRole("button", { name: manual.submit }));

    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/admin/orders/ORD-MANUAL01/pre-invoice"),
    );
    expect(captured).toMatchObject({
      items: [{ sku: "HB-250", quantity: 2 }],
      shipping_address: { recipient_name: "Sara Ahmadi", postal_code: "1234567890" },
    });
  });

  it("supports adding and removing line rows", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ManualOrderForm />);

    // One row initially: no remove control.
    expect(screen.queryByRole("button", { name: manual.removeItem })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: manual.addItem }));
    const removes = screen.getAllByRole("button", { name: manual.removeItem });
    expect(removes).toHaveLength(2);

    await user.click(removes[0]);
    expect(screen.queryByRole("button", { name: manual.removeItem })).not.toBeInTheDocument();
  });

  it("shows a localized error when the backend rejects the order", async () => {
    server.use(
      http.post("*/orders/manual/", () =>
        HttpResponse.json({ detail: "out of stock" }, { status: 409 }),
      ),
    );

    renderWithProviders(<ManualOrderForm />);
    const user = await fillAddress();
    await user.type(screen.getByLabelText(manual.sku), "HB-250");
    await user.click(screen.getByRole("button", { name: manual.submit }));

    expect(await screen.findByText(manual.error)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});

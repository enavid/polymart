import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { ChannelsManager } from "@/components/admin/channels-manager";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const coffee = {
  id: 1,
  slug: "coffee-ir",
  name: "Coffee IR",
  currency: "IRR",
  is_active: true,
};

describe("ChannelsManager", () => {
  it("lists channels with their status", async () => {
    server.use(http.get("*/channels/", () => HttpResponse.json([coffee])));

    renderWithProviders(<ChannelsManager />);

    expect(await screen.findByText("coffee-ir")).toBeInTheDocument();
    expect(screen.getByText("IRR")).toBeInTheDocument();
    expect(screen.getByText(messages.channels.active)).toBeInTheDocument();
  });

  it("shows an empty state when there are no channels", async () => {
    server.use(http.get("*/channels/", () => HttpResponse.json([])));

    renderWithProviders(<ChannelsManager />);
    expect(
      await screen.findByText(messages.channels.noChannels),
    ).toBeInTheDocument();
  });

  it("creates a channel and refreshes the list", async () => {
    let created = false;
    server.use(
      http.get("*/channels/", () =>
        HttpResponse.json(created ? [coffee] : []),
      ),
      http.post("*/channels/", async () => {
        created = true;
        return HttpResponse.json(coffee, { status: 201 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<ChannelsManager />);

    await screen.findByText(messages.channels.noChannels);
    await user.type(screen.getByLabelText(messages.channels.slug), "coffee-ir");
    await user.type(screen.getByLabelText(messages.channels.name), "Coffee IR");
    await user.type(screen.getByLabelText(messages.channels.currency), "irr");
    await user.click(
      screen.getByRole("button", { name: messages.channels.createCta }),
    );

    expect(await screen.findByText("coffee-ir")).toBeInTheDocument();
  });

  it("maps a 409 conflict to the already-exists message", async () => {
    server.use(
      http.get("*/channels/", () => HttpResponse.json([])),
      http.post("*/channels/", () =>
        HttpResponse.json({ detail: "exists" }, { status: 409 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<ChannelsManager />);

    await screen.findByText(messages.channels.noChannels);
    await user.type(screen.getByLabelText(messages.channels.slug), "coffee-ir");
    await user.type(screen.getByLabelText(messages.channels.name), "Coffee IR");
    await user.type(screen.getByLabelText(messages.channels.currency), "IRR");
    await user.click(
      screen.getByRole("button", { name: messages.channels.createCta }),
    );

    expect(
      await screen.findByText(messages.channels.alreadyExists),
    ).toBeInTheDocument();
  });

  it("toggles a channel's active status", async () => {
    let active = true;
    let patched: unknown;
    server.use(
      http.get("*/channels/", () =>
        HttpResponse.json([{ ...coffee, is_active: active }]),
      ),
      http.patch("*/channels/coffee-ir/", async ({ request }) => {
        patched = await request.json();
        active = false;
        return HttpResponse.json({ ...coffee, is_active: false });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<ChannelsManager />);

    await screen.findByText("coffee-ir");
    await user.click(
      screen.getByRole("button", { name: messages.channels.deactivate }),
    );

    await waitFor(() => expect(patched).toEqual({ is_active: false }));
    expect(
      await screen.findByText(messages.channels.inactive),
    ).toBeInTheDocument();
  });
});

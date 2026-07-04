import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { CollectionsManager } from "@/components/admin/catalog/collections-manager";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const summer = { id: 1, slug: "summer", name: "Summer" };

describe("CollectionsManager", () => {
  it("lists collections with a manage link", async () => {
    server.use(
      http.get("*/catalog/collections/", () => HttpResponse.json([summer])),
    );

    renderWithProviders(<CollectionsManager />);

    expect(await screen.findByText("summer")).toBeInTheDocument();
    expect(screen.getByText("Summer")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: messages.catalog.collections.manage }),
    ).toHaveAttribute("href", "/manage/catalog/collections/summer");
  });

  it("shows an empty state when there are no collections", async () => {
    server.use(http.get("*/catalog/collections/", () => HttpResponse.json([])));

    renderWithProviders(<CollectionsManager />);
    expect(
      await screen.findByText(messages.catalog.collections.empty),
    ).toBeInTheDocument();
  });

  it("creates a collection and refreshes the list", async () => {
    let created = false;
    server.use(
      http.get("*/catalog/collections/", () =>
        HttpResponse.json(created ? [summer] : []),
      ),
      http.post("*/catalog/collections/", async () => {
        created = true;
        return HttpResponse.json(summer, { status: 201 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<CollectionsManager />);

    await screen.findByText(messages.catalog.collections.empty);
    await user.type(screen.getByLabelText(messages.catalog.slug), "summer");
    await user.type(screen.getByLabelText(messages.catalog.name), "Summer");
    await user.click(
      screen.getByRole("button", { name: messages.catalog.create }),
    );

    expect(await screen.findByText("summer")).toBeInTheDocument();
  });
});

import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { CollectionDetail } from "@/components/admin/catalog/collection-detail";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function mockReads() {
  server.use(
    http.get("*/catalog/collections/summer/products/", () =>
      HttpResponse.json({ products: ["a", "b"] }),
    ),
    http.get("*/catalog/collections/summer/rule/", () =>
      HttpResponse.json({ conditions: [] }),
    ),
    http.get("*/catalog/collections/summer/rule/members/", () =>
      HttpResponse.json({ products: ["a"] }),
    ),
  );
}

describe("CollectionDetail", () => {
  it("seeds the members field from the manual member list", async () => {
    mockReads();

    renderWithProviders(<CollectionDetail slug="summer" />);

    expect(await screen.findByDisplayValue("a, b")).toBeInTheDocument();
  });

  it("computes rule members on demand", async () => {
    mockReads();

    const user = userEvent.setup();
    renderWithProviders(<CollectionDetail slug="summer" />);

    await screen.findByDisplayValue("a, b");
    await user.click(
      screen.getByRole("button", {
        name: messages.catalog.collectionDetail.refreshMembers,
      }),
    );

    expect(await screen.findByText("a")).toBeInTheDocument();
  });
});

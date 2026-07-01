import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { AttributesManager } from "@/components/admin/catalog/attributes-manager";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const color = {
  id: 1,
  code: "color",
  name: "Color",
  input_type: "dropdown",
  required: true,
  choices: [],
};

describe("AttributesManager", () => {
  it("lists attributes with their fields", async () => {
    server.use(
      http.get("*/catalog/attributes/", () => HttpResponse.json([color])),
    );

    renderWithProviders(<AttributesManager />);

    expect(await screen.findByText("color")).toBeInTheDocument();
    expect(screen.getByText("Color")).toBeInTheDocument();
    expect(screen.getByText("dropdown")).toBeInTheDocument();
  });

  it("shows an empty state when there are no attributes", async () => {
    server.use(http.get("*/catalog/attributes/", () => HttpResponse.json([])));

    renderWithProviders(<AttributesManager />);

    expect(
      await screen.findByText(messages.catalog.attributes.empty),
    ).toBeInTheDocument();
  });

  it("creates an attribute and refreshes the list", async () => {
    let created = false;
    server.use(
      http.get("*/catalog/attributes/", () =>
        HttpResponse.json(created ? [color] : []),
      ),
      http.post("*/catalog/attributes/", async () => {
        created = true;
        return HttpResponse.json(color, { status: 201 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AttributesManager />);

    await screen.findByText(messages.catalog.attributes.empty);
    await user.type(screen.getByLabelText(messages.catalog.code), "color");
    await user.type(screen.getByLabelText(messages.catalog.name), "Color");
    await user.click(
      screen.getByRole("button", { name: messages.catalog.create }),
    );

    expect(await screen.findByText("color")).toBeInTheDocument();
  });
});

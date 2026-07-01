import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { ImportExport } from "@/components/admin/catalog/import-export";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("ImportExport", () => {
  it("renders the export action", () => {
    renderWithProviders(<ImportExport />);

    expect(
      screen.getByRole("button", {
        name: messages.catalog.importExport.exportCta,
      }),
    ).toBeInTheDocument();
  });

  it("imports a CSV and reports the created count", async () => {
    server.use(
      http.post("*/catalog/products/import/", () =>
        HttpResponse.json({ created: 1, errors: [] }, { status: 200 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<ImportExport />);

    const file = new File(["code,name,product_type\n"], "p.csv", {
      type: "text/csv",
    });
    await user.upload(
      screen.getByLabelText(messages.catalog.importExport.chooseFile),
      file,
    );
    await user.click(
      screen.getByRole("button", {
        name: messages.catalog.importExport.importCta,
      }),
    );

    expect(
      await screen.findByText((content) => content.includes("1")),
    ).toBeInTheDocument();
  });

  it("renders per-row errors on a failed import", async () => {
    server.use(
      http.post("*/catalog/products/import/", () =>
        HttpResponse.json(
          {
            created: 0,
            errors: [
              { row_number: 2, code: "ghost", error: "unknown product type" },
            ],
          },
          { status: 400 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<ImportExport />);

    const file = new File(["code,name,product_type\n"], "p.csv", {
      type: "text/csv",
    });
    await user.upload(
      screen.getByLabelText(messages.catalog.importExport.chooseFile),
      file,
    );
    await user.click(
      screen.getByRole("button", {
        name: messages.catalog.importExport.importCta,
      }),
    );

    expect(
      await screen.findByText("unknown product type"),
    ).toBeInTheDocument();
  });
});

import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { AuditViewer } from "@/components/admin/audit-viewer";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("AuditViewer", () => {
  it("renders audit entries with actor and a change summary", async () => {
    server.use(
      http.get("*/audit/entries/", () =>
        HttpResponse.json([
          {
            action: "channel.status_changed",
            resource_type: "channel",
            resource_id: "3",
            actor: "42",
            occurred_at: "2026-06-29T09:30:00Z",
            changes: { is_active: { before: true, after: false } },
          },
        ]),
      ),
    );

    renderWithProviders(<AuditViewer />);

    expect(
      await screen.findByText("channel.status_changed"),
    ).toBeInTheDocument();
    expect(screen.getByText("channel:3")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText(/is_active: true → false/)).toBeInTheDocument();
  });

  it("labels a null actor as system", async () => {
    server.use(
      http.get("*/audit/entries/", () =>
        HttpResponse.json([
          {
            action: "x.created",
            resource_type: "x",
            resource_id: "1",
            actor: null,
            occurred_at: "2026-06-29T09:30:00Z",
            changes: {},
          },
        ]),
      ),
    );

    renderWithProviders(<AuditViewer />);
    expect(await screen.findByText(messages.audit.system)).toBeInTheDocument();
  });

  it("shows an empty state when there are no entries", async () => {
    server.use(http.get("*/audit/entries/", () => HttpResponse.json([])));

    renderWithProviders(<AuditViewer />);
    expect(await screen.findByText(messages.audit.noEntries)).toBeInTheDocument();
  });

  it("shows an error when the caller is forbidden", async () => {
    server.use(
      http.get("*/audit/entries/", () =>
        HttpResponse.json({ detail: "forbidden" }, { status: 403 }),
      ),
    );

    renderWithProviders(<AuditViewer />);
    expect(await screen.findByText("forbidden")).toBeInTheDocument();
  });
});

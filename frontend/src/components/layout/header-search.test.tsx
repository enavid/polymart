import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { HeaderSearch } from "@/components/layout/header-search";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const push = vi.fn();
let currentParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => currentParams,
}));

const search = messages.storefront.search;

describe("HeaderSearch", () => {
  it("navigates to the storefront with the typed term", async () => {
    push.mockClear();
    currentParams = new URLSearchParams();
    const user = userEvent.setup();
    renderWithProviders(<HeaderSearch />);

    await user.type(screen.getByRole("searchbox", { name: search }), "کفش");
    await user.keyboard("{Enter}");

    expect(push).toHaveBeenCalledWith(`/products?q=${encodeURIComponent("کفش")}`);
  });

  it("navigates to the bare storefront when the term is empty", async () => {
    push.mockClear();
    currentParams = new URLSearchParams();
    const user = userEvent.setup();
    renderWithProviders(<HeaderSearch />);

    // Submit with only whitespace: no query param, just the listing.
    await user.type(screen.getByRole("searchbox", { name: search }), "   {Enter}");

    expect(push).toHaveBeenCalledWith("/products");
  });

  it("seeds the field from the current q param", () => {
    push.mockClear();
    currentParams = new URLSearchParams("q=قهوه");
    renderWithProviders(<HeaderSearch />);

    expect(screen.getByRole("searchbox", { name: search })).toHaveValue("قهوه");
  });
});

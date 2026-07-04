import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AccountMenu } from "@/components/layout/account-menu";
import type { UserProfile } from "@/lib/api/auth";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const nav = messages.nav;

const shopper: UserProfile = {
  id: 1,
  phone_number: "+989123456789",
  email: "",
  full_name: "Sara Ahmadi",
  is_staff: false,
};

const staff: UserProfile = { ...shopper, id: 2, is_staff: true };

describe("AccountMenu", () => {
  it("hides the account areas until the trigger is opened", () => {
    renderWithProviders(
      <AccountMenu user={shopper} onLogout={() => {}} loggingOut={false} />,
    );

    const trigger = screen.getByRole("button", { name: /Sara Ahmadi/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("reveals orders and addresses inside the account hub, not the top nav", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <AccountMenu user={shopper} onLogout={() => {}} loggingOut={false} />,
    );

    await user.click(screen.getByRole("button", { name: /Sara Ahmadi/ }));

    expect(screen.getByRole("menuitem", { name: nav.orders })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: nav.addresses })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: nav.account })).toBeInTheDocument();
  });

  it("shows the admin entry only for staff", async () => {
    const user = userEvent.setup();
    const { rerender } = renderWithProviders(
      <AccountMenu user={shopper} onLogout={() => {}} loggingOut={false} />,
    );
    await user.click(screen.getByRole("button", { name: /Sara Ahmadi/ }));
    expect(screen.queryByRole("menuitem", { name: nav.admin })).not.toBeInTheDocument();

    // The menu stays open across the prop change; staff now sees the admin entry.
    rerender(<AccountMenu user={staff} onLogout={() => {}} loggingOut={false} />);
    expect(screen.getByRole("menuitem", { name: nav.admin })).toBeInTheDocument();
  });

  it("invokes the logout handler from the menu", async () => {
    const user = userEvent.setup();
    const onLogout = vi.fn();
    renderWithProviders(
      <AccountMenu user={shopper} onLogout={onLogout} loggingOut={false} />,
    );

    await user.click(screen.getByRole("button", { name: /Sara Ahmadi/ }));
    await user.click(screen.getByRole("menuitem", { name: nav.logout }));

    expect(onLogout).toHaveBeenCalledOnce();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <AccountMenu user={shopper} onLogout={() => {}} loggingOut={false} />,
    );

    await user.click(screen.getByRole("button", { name: /Sara Ahmadi/ }));
    expect(screen.getByRole("menu")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});

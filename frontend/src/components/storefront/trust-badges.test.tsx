import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { TrustBadges } from "@/components/storefront/trust-badges";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

describe("TrustBadges", () => {
  it("lists the store-wide reassurance guarantees", () => {
    renderWithProviders(<TrustBadges />);

    expect(screen.getByText(messages.home.trustAuthenticTitle)).toBeInTheDocument();
    expect(screen.getByText(messages.home.trustReturnsTitle)).toBeInTheDocument();
    expect(screen.getByText(messages.home.trustPaymentTitle)).toBeInTheDocument();
    expect(screen.getByText(messages.home.trustShippingTitle)).toBeInTheDocument();
  });
});

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Loading } from "@/components/ui/spinner";

describe("Loading", () => {
  it("announces the busy state with a status role and label", () => {
    render(<Loading label="در حال بارگذاری" />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("در حال بارگذاری");
  });
});

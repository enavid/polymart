import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ProductThumb } from "@/components/storefront/product-thumb";

describe("ProductThumb", () => {
  it("renders the product image when one is provided", () => {
    render(
      <ProductThumb
        name="House Blend"
        image={{ url: "https://cdn.example.com/hb.jpg", alt_text: "House Blend bag" }}
      />,
    );

    const img = screen.getByRole("img", { name: "House Blend bag" });
    expect(img).toHaveAttribute("src", "https://cdn.example.com/hb.jpg");
  });

  it("falls back to the product name as alt text when the image has none", () => {
    render(
      <ProductThumb name="House Blend" image={{ url: "https://cdn.example.com/hb.jpg", alt_text: "" }} />,
    );

    expect(screen.getByRole("img", { name: "House Blend" })).toBeInTheDocument();
  });

  it("shows a monogram placeholder (no image) when there is no image", () => {
    render(<ProductThumb name="House Blend" />);

    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText("H")).toBeInTheDocument();
  });

  it("renders the placeholder on the neutral muted surface, not a loud tile", () => {
    const { container } = render(<ProductThumb name="House Blend" />);
    const tile = container.querySelector("[aria-hidden]") as HTMLElement;
    // The placeholder stays inside the design system's neutral palette.
    expect(tile.className).toContain("bg-muted");
    expect(tile.className).toContain("text-muted-foreground");
  });
});

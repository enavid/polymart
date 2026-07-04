import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ProductThumb, THUMB_TONES, toneIndex } from "@/components/storefront/product-thumb";

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

  it("picks a stable tone from the name so a catalog reads as varied covers", () => {
    // Deterministic: same name ⇒ same tone; and it indexes a real palette entry.
    expect(toneIndex("House Blend")).toBe(toneIndex("House Blend"));
    expect(toneIndex("House Blend")).toBeLessThan(THUMB_TONES.length);
    // Two different names generally land on different tones (these two differ).
    expect(toneIndex("تی‌شرت نخی")).not.toBe(toneIndex("شلوار جین"));
  });

  it("paints the monogram tile with its name's gradient tone", () => {
    const { container } = render(<ProductThumb name="House Blend" />);
    const tile = container.querySelector("[aria-hidden]") as HTMLElement;
    const [from] = THUMB_TONES[toneIndex("House Blend")];
    expect(tile.style.backgroundImage).toContain(from);
  });
});

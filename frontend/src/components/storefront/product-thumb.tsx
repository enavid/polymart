import type { VariantMedia } from "@/lib/api/catalog";
import { cn } from "@/lib/utils";

/**
 * A product thumbnail. When the product has a primary image (promoted from one of
 * its variants by the storefront read) it renders that photo; otherwise it fills
 * the card with a calm, neutral panel carrying the product's monogram, so a
 * product without imagery never leaves an empty box.
 *
 * The placeholder is deliberately quiet -- one muted surface that sits inside the
 * neutral design system rather than a loud coloured tile -- and purely
 * presentational: `aria-hidden` keeps it out of the accessibility tree (the
 * product name is already the card's heading).
 */
export function ProductThumb({
  name,
  image,
  className,
}: {
  name: string;
  image?: VariantMedia | null;
  className?: string;
}) {
  if (image) {
    return (
      // A white-label store pulls product photos from arbitrary merchant CDNs, so
      // next/image (which needs each host whitelisted) is not usable here; a plain
      // lazy <img> is the pragmatic choice.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={image.url}
        alt={image.alt_text || name}
        loading="lazy"
        className={cn("aspect-[4/3] w-full bg-muted object-cover", className)}
      />
    );
  }

  // First visible character as a monogram; falls back to a dot for empty names.
  const monogram = Array.from(name.trim())[0] ?? "·";

  return (
    <div
      aria-hidden
      className={cn(
        "flex aspect-[4/3] w-full items-center justify-center bg-muted text-muted-foreground",
        className,
      )}
    >
      <span className="text-4xl font-semibold opacity-60 select-none">{monogram}</span>
    </div>
  );
}

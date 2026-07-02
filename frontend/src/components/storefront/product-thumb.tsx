import type { VariantMedia } from "@/lib/api/catalog";
import { cn } from "@/lib/utils";

/**
 * A product thumbnail. When the product has a primary image (promoted from one of
 * its variants by the storefront read) it renders that photo; otherwise it fills
 * the card with a warm branded panel carrying the product's monogram, so a product
 * without imagery never leaves an empty box.
 *
 * The placeholder is purely presentational: `aria-hidden` keeps it out of the
 * accessibility tree (the product name is already the card's heading), so it adds
 * no duplicate accessible name. The real image keeps its alt text (falling back to
 * the product name) because it carries meaning.
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
        className={cn("aspect-[4/3] w-full object-cover", className)}
      />
    );
  }

  // First visible character as a monogram; falls back to a dot for empty names.
  const monogram = Array.from(name.trim())[0] ?? "·";

  return (
    <div
      aria-hidden
      className={cn(
        "flex aspect-[4/3] w-full items-center justify-center bg-[image:linear-gradient(135deg,var(--hero-from),var(--hero-to))] text-primary-foreground",
        className,
      )}
    >
      <span className="text-4xl font-bold opacity-90 select-none">{monogram}</span>
    </div>
  );
}

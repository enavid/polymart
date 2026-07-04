import type { VariantMedia } from "@/lib/api/catalog";
import { cn } from "@/lib/utils";

/**
 * A product thumbnail. When the product has a primary image (promoted from one of
 * its variants by the storefront read) it renders that photo; otherwise it fills
 * the card with a branded gradient panel carrying the product's monogram, so a
 * product without imagery never leaves an empty box.
 *
 * The placeholder is purely presentational: `aria-hidden` keeps it out of the
 * accessibility tree (the product name is already the card's heading). Its tone is
 * picked deterministically from the product name out of a small, curated palette,
 * so a large catalog reads as a varied set of covers rather than one repeated
 * colour — while every tone stays cohesive and works on both light and dark.
 */

/** Curated gradient pairs (all mid-tone, white-monogram-safe in either theme). */
export const THUMB_TONES: readonly (readonly [string, string])[] = [
  ["#4f46e5", "#7c3aed"], // indigo → violet (brand)
  ["#2563eb", "#4f46e5"], // blue → indigo
  ["#0891b2", "#2563eb"], // cyan → blue
  ["#0d9488", "#0891b2"], // teal → cyan
  ["#059669", "#0d9488"], // emerald → teal
  ["#d97706", "#db2777"], // amber → pink
  ["#db2777", "#7c3aed"], // pink → violet
  ["#e11d48", "#d97706"], // rose → amber
];

/** Stable index into THUMB_TONES from a name (same name ⇒ same tone every render). */
export function toneIndex(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  }
  return hash % THUMB_TONES.length;
}

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
  const [from, to] = THUMB_TONES[toneIndex(name)];

  return (
    <div
      aria-hidden
      style={{ backgroundImage: `linear-gradient(135deg, ${from}, ${to})` }}
      className={cn(
        "flex aspect-[4/3] w-full items-center justify-center text-white",
        className,
      )}
    >
      <span className="text-4xl font-bold opacity-90 select-none">{monogram}</span>
    </div>
  );
}

import { cn } from "@/lib/utils";

/**
 * A decorative product thumbnail. Products have no image yet (media is a later
 * slice -- see ISSUES.md), so this fills the card with a warm branded panel
 * carrying the product's monogram instead of leaving an empty box.
 *
 * It is purely presentational: `aria-hidden` keeps it out of the accessibility
 * tree (the product name is already the card's heading), so it adds no
 * duplicate accessible name.
 */
export function ProductThumb({ name, className }: { name: string; className?: string }) {
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

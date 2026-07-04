import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

/** A spinning loader glyph. Use inside buttons or beside text for busy states. */
export function Spinner({ className }: { className?: string }) {
  return <Loader2 aria-hidden className={cn("h-5 w-5 animate-spin", className)} />;
}

/**
 * A centred loading indicator for a section that is fetching its data: a spinning
 * circle beside a label. `role="status"` + `aria-live` announce it to assistive
 * tech, so a slow network reads as "loading", not a frozen page.
 */
export function Loading({ label }: { label: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-3 py-12 text-muted-foreground"
    >
      <Spinner className="text-primary" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

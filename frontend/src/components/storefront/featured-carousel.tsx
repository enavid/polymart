"use client";

import { useEffect, useRef } from "react";
import { useTranslations } from "next-intl";

import { ProductCard } from "@/components/storefront/product-card";
import type { StorefrontProduct } from "@/lib/api/catalog";

/** Auto-advance interval for the featured carousel (ms). */
const AUTO_ADVANCE_MS = 5000;
/** How far the near-end check tolerates sub-pixel scroll rounding. */
const END_EPSILON = 4;

/**
 * An auto-rotating, swipeable carousel of admin-curated featured products.
 *
 * Mechanics run on a native scroll-snap track forced to LTR so `scrollLeft`
 * math stays browser-consistent (the card *content* stays RTL). This gives touch
 * swipe and responsive per-view counts for free; a timer advances one viewport at
 * a time and loops back at the end, and it pauses while the pointer/focus is
 * inside so it never yanks the page out from under a reader.
 *
 * `autoAdvance` is on by default (the landing's top strip); the home page's
 * per-category rows pass it off, since several tracks rotating at once would be
 * distracting rather than helpful. Manual prev/next always work either way.
 */
export function FeaturedCarousel({
  products,
  autoAdvance = true,
}: {
  products: StorefrontProduct[];
  autoAdvance?: boolean;
}) {
  const t = useTranslations("home");
  const trackRef = useRef<HTMLDivElement>(null);
  const pausedRef = useRef(false);

  const step = (direction: 1 | -1) => {
    const track = trackRef.current;
    if (!track) {
      return;
    }
    const amount = track.clientWidth * 0.9;
    const atEnd = track.scrollLeft + track.clientWidth >= track.scrollWidth - END_EPSILON;
    if (direction === 1 && atEnd) {
      track.scrollTo?.({ left: 0, behavior: "smooth" });
    } else {
      track.scrollBy?.({ left: direction * amount, behavior: "smooth" });
    }
  };

  useEffect(() => {
    if (!autoAdvance || products.length <= 1) {
      return;
    }
    const id = window.setInterval(() => {
      if (!pausedRef.current) {
        step(1);
      }
    }, AUTO_ADVANCE_MS);
    return () => window.clearInterval(id);
  }, [autoAdvance, products.length]);

  return (
    <div
      className="relative"
      onMouseEnter={() => (pausedRef.current = true)}
      onMouseLeave={() => (pausedRef.current = false)}
      onFocusCapture={() => (pausedRef.current = true)}
      onBlurCapture={() => (pausedRef.current = false)}
    >
      <div
        ref={trackRef}
        dir="ltr"
        className="flex snap-x snap-mandatory gap-5 overflow-x-auto scroll-smooth pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {products.map((product) => (
          <div
            key={product.code}
            dir="rtl"
            className="min-w-[80%] shrink-0 snap-start sm:min-w-[45%] lg:min-w-[31%] xl:min-w-[23%]"
          >
            <ProductCard product={product} />
          </div>
        ))}
      </div>

      {products.length > 1 ? (
        <>
          <CarouselButton side="start" label={t("carouselPrevious")} onClick={() => step(-1)} />
          <CarouselButton side="end" label={t("carouselNext")} onClick={() => step(1)} />
        </>
      ) : null}
    </div>
  );
}

function CarouselButton({
  side,
  label,
  onClick,
}: {
  side: "start" | "end";
  label: string;
  onClick: () => void;
}) {
  const position = side === "start" ? "start-1" : "end-1";
  // The chevron points "inward": toward the start button on the start side.
  const glyph = side === "start" ? "‹" : "›";
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={`absolute top-1/2 ${position} z-10 hidden h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-background/90 text-lg text-foreground shadow-md backdrop-blur transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:flex`}
    >
      <span aria-hidden>{glyph}</span>
    </button>
  );
}

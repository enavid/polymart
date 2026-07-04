"use client";

import { Lock, RotateCcw, ShieldCheck, Truck } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ComponentType } from "react";

/**
 * A reassurance strip of the promises Iranian shoppers scan a store for before
 * they trust it: genuine goods, an easy return window, secure payment, and fast
 * delivery. Purely presentational and static -- these are store-wide guarantees,
 * not data -- so it always renders. Icons are decorative; the label carries the
 * meaning.
 */
export function TrustBadges() {
  const t = useTranslations("home");

  const badges: { icon: ComponentType<{ className?: string }>; title: string; desc: string }[] = [
    { icon: ShieldCheck, title: t("trustAuthenticTitle"), desc: t("trustAuthenticDesc") },
    { icon: RotateCcw, title: t("trustReturnsTitle"), desc: t("trustReturnsDesc") },
    { icon: Lock, title: t("trustPaymentTitle"), desc: t("trustPaymentDesc") },
    { icon: Truck, title: t("trustShippingTitle"), desc: t("trustShippingDesc") },
  ];

  return (
    <section className="grid grid-cols-2 gap-4 rounded-2xl border border-border bg-card p-5 sm:grid-cols-4 sm:p-6">
      {badges.map(({ icon: Icon, title, desc }) => (
        <div key={title} className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-muted text-primary">
            <Icon className="h-5 w-5" />
          </span>
          <div className="flex flex-col">
            <span className="text-sm font-semibold text-foreground">{title}</span>
            <span className="text-xs text-muted-foreground">{desc}</span>
          </div>
        </div>
      ))}
    </section>
  );
}

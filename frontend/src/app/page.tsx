import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { fetchHealth } from "@/lib/api/health";

export default async function HomePage() {
  const t = await getTranslations("common");
  const tNav = await getTranslations("nav");
  let backendState = "unknown";
  try {
    const report = await fetchHealth();
    backendState = report.state;
  } catch {
    backendState = "unreachable";
  }

  return (
    <section className="flex flex-col gap-3">
      <h1 className="text-2xl font-bold">Polymart</h1>
      <p className="text-muted-foreground">{t("appName")}</p>
      <nav className="flex gap-4 text-sm">
        <Link href="/products" className="underline">
          {tNav("storefront")}
        </Link>
        <Link href="/admin" className="underline">
          {tNav("admin")}
        </Link>
      </nav>
      <p data-testid="backend-state" className="text-sm">
        Backend status: {backendState}
      </p>
    </section>
  );
}

import { getTranslations } from "next-intl/server";

import { fetchHealth } from "@/lib/api/health";

export default async function HomePage() {
  const t = await getTranslations("common");
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
      <p data-testid="backend-state" className="text-sm">
        Backend status: {backendState}
      </p>
    </section>
  );
}

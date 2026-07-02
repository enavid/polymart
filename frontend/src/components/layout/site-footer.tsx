import { getTranslations } from "next-intl/server";

/** Site-wide footer: brand, tagline, and a dynamic-year copyright line. */
export async function SiteFooter() {
  const t = await getTranslations("footer");
  const tCommon = await getTranslations("common");
  const year = new Date().getFullYear();

  return (
    <footer className="mt-auto border-t border-border">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-1 px-4 py-6 text-sm text-muted-foreground">
        <span className="font-semibold text-foreground">{tCommon("appName")}</span>
        <span>{t("tagline")}</span>
        <span>
          © {year} {tCommon("appName")} — {t("rights")}
        </span>
      </div>
    </footer>
  );
}

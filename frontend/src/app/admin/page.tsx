import { getTranslations } from "next-intl/server";
import Link from "next/link";

/**
 * Admin hub. A discoverable landing that links every management area, so staff
 * reach any capability from one place instead of typing deep URLs. Access to
 * `/admin/*` is enforced by the pages themselves (staff-only); this is just
 * navigation.
 */
export default async function AdminIndexPage() {
  const t = await getTranslations("nav");
  const tAdmin = await getTranslations("admin");

  const areas: { href: string; title: string; desc: string }[] = [
    { href: "/admin/catalog", title: t("catalog"), desc: tAdmin("hubCatalog") },
    { href: "/admin/access", title: t("access"), desc: tAdmin("hubAccess") },
    { href: "/admin/channels", title: t("channels"), desc: tAdmin("hubChannels") },
    { href: "/admin/orders/new", title: t("manualOrders"), desc: tAdmin("hubManualOrders") },
    { href: "/admin/audit", title: t("audit"), desc: tAdmin("hubAudit") },
    { href: "/admin/catalog/import-export", title: tAdmin("hubImportExportTitle"), desc: tAdmin("hubImportExport") },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{tAdmin("title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{tAdmin("hubSubtitle")}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {areas.map((area) => (
          <Link
            key={area.href}
            href={area.href}
            className="group rounded-xl border border-border bg-card p-5 shadow-sm transition-colors hover:border-primary hover:bg-accent"
          >
            <div className="text-base font-semibold text-card-foreground group-hover:text-accent-foreground">
              {area.title}
            </div>
            <p className="mt-1.5 text-sm text-muted-foreground">{area.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}

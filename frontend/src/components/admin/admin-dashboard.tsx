"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { listUsers } from "@/lib/api/access";
import { listProducts } from "@/lib/api/catalog";
import { listChannels } from "@/lib/api/channels";

function faNumber(value: number | undefined): string {
  return value === undefined ? "—" : new Intl.NumberFormat("fa-IR").format(value);
}

/**
 * Admin landing dashboard: at-a-glance KPIs (counts pulled from the management
 * read APIs) plus quick links into every management area. Replaces the old flat
 * grid of link tiles with a real overview.
 */
export function AdminDashboard() {
  const t = useTranslations("nav");
  const tAdmin = useTranslations("admin");

  const products = useQuery({ queryKey: ["admin-kpi-products"], queryFn: () => listProducts() });
  const channels = useQuery({ queryKey: ["admin-kpi-channels"], queryFn: () => listChannels() });
  const users = useQuery({
    queryKey: ["admin-kpi-users"],
    queryFn: () => listUsers({ limit: 1 }),
  });

  const kpis = [
    { label: tAdmin("kpiProducts"), value: products.data?.length, href: "/admin/catalog/products" },
    { label: tAdmin("kpiChannels"), value: channels.data?.length, href: "/admin/channels" },
    { label: tAdmin("kpiUsers"), value: users.data?.count, href: "/admin/access" },
  ];

  const areas = [
    { href: "/admin/catalog", title: t("catalog"), desc: tAdmin("hubCatalog") },
    { href: "/admin/access", title: t("access"), desc: tAdmin("hubAccess") },
    { href: "/admin/channels", title: t("channels"), desc: tAdmin("hubChannels") },
    { href: "/admin/orders/new", title: t("manualOrders"), desc: tAdmin("hubManualOrders") },
    { href: "/admin/audit", title: t("audit"), desc: tAdmin("hubAudit") },
    {
      href: "/admin/catalog/import-export",
      title: tAdmin("hubImportExportTitle"),
      desc: tAdmin("hubImportExport"),
    },
  ];

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{tAdmin("dashboard")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{tAdmin("dashboardSubtitle")}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {kpis.map((kpi) => (
          <Link
            key={kpi.href}
            href={kpi.href}
            className="rounded-xl border border-border bg-card p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
          >
            <p className="text-sm text-muted-foreground">{kpi.label}</p>
            <p className="mt-2 text-3xl font-bold tracking-tight text-foreground">
              {faNumber(kpi.value)}
            </p>
          </Link>
        ))}
      </div>

      <div className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold tracking-tight">{tAdmin("quickLinks")}</h2>
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
    </div>
  );
}

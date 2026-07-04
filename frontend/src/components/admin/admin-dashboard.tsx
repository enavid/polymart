"use client";

import { useQuery } from "@tanstack/react-query";
import { type LucideIcon, Package, Receipt, ScrollText, Store, Users } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Alert } from "@/components/ui/alert";
import { listUsers } from "@/lib/api/access";
import { listProducts } from "@/lib/api/catalog";
import { listChannels } from "@/lib/api/channels";

function faNumber(value: number | undefined): string {
  return value === undefined ? "—" : new Intl.NumberFormat("fa-IR").format(value);
}

/**
 * Admin landing dashboard: at-a-glance KPIs (counts pulled from the management
 * read APIs) plus quick links into every management area. KPIs carry an icon,
 * show a skeleton while loading, and surface a single error banner if any count
 * fails to load rather than sitting silently on a dash.
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

  const kpis: {
    label: string;
    value: number | undefined;
    href: string;
    Icon: LucideIcon;
    loading: boolean;
  }[] = [
    {
      label: tAdmin("kpiProducts"),
      value: products.data?.length,
      href: "/manage/catalog/products",
      Icon: Package,
      loading: products.isLoading,
    },
    {
      label: tAdmin("kpiChannels"),
      value: channels.data?.length,
      href: "/manage/channels",
      Icon: Store,
      loading: channels.isLoading,
    },
    {
      label: tAdmin("kpiUsers"),
      value: users.data?.count,
      href: "/manage/access",
      Icon: Users,
      loading: users.isLoading,
    },
  ];

  const kpiError = products.isError || channels.isError || users.isError;

  const areas: { href: string; title: string; desc: string; Icon: LucideIcon }[] = [
    { href: "/manage/catalog", title: t("catalog"), desc: tAdmin("hubCatalog"), Icon: Package },
    { href: "/manage/access", title: t("access"), desc: tAdmin("hubAccess"), Icon: Users },
    { href: "/manage/channels", title: t("channels"), desc: tAdmin("hubChannels"), Icon: Store },
    {
      href: "/manage/orders/new",
      title: t("manualOrders"),
      desc: tAdmin("hubManualOrders"),
      Icon: Receipt,
    },
    { href: "/manage/audit", title: t("audit"), desc: tAdmin("hubAudit"), Icon: ScrollText },
  ];

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{tAdmin("dashboard")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{tAdmin("dashboardSubtitle")}</p>
      </div>

      {kpiError ? <Alert variant="destructive">{tAdmin("kpiLoadError")}</Alert> : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {kpis.map((kpi) => {
          const { Icon } = kpi;
          return (
            <Link
              key={kpi.href}
              href={kpi.href}
              className="flex items-center gap-4 rounded-xl border border-border bg-card p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
            >
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon aria-hidden className="h-6 w-6" />
              </span>
              <div className="min-w-0">
                <p className="text-sm text-muted-foreground">{kpi.label}</p>
                {kpi.loading ? (
                  <span className="mt-2 block h-8 w-16 animate-pulse rounded bg-muted" />
                ) : (
                  <p className="mt-1 text-3xl font-bold tracking-tight text-foreground">
                    {faNumber(kpi.value)}
                  </p>
                )}
              </div>
            </Link>
          );
        })}
      </div>

      <div className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold tracking-tight">{tAdmin("quickLinks")}</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {areas.map((area) => {
            const { Icon } = area;
            return (
              <Link
                key={area.href}
                href={area.href}
                className="group flex items-start gap-4 rounded-xl border border-border bg-card p-5 shadow-sm transition-colors hover:border-primary hover:bg-accent"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground transition-colors group-hover:bg-primary/10 group-hover:text-primary">
                  <Icon aria-hidden className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <div className="text-base font-semibold text-card-foreground group-hover:text-accent-foreground">
                    {area.title}
                  </div>
                  <p className="mt-1.5 text-sm text-muted-foreground">{area.desc}</p>
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";
import { useCurrentUser, useLogout } from "@/lib/hooks/use-auth";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

/** Whether a nav item is the active section (exact for the dashboard root, prefix
 *  for the rest so sub-pages keep their section highlighted). */
function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) {
    return false;
  }
  return href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);
}

/**
 * The dedicated admin panel shell: a persistent sidebar of grouped sections and
 * an admin top bar with its own identity, a back-to-store link, theme control,
 * and sign-out. Full width — the content area uses all the horizontal space
 * rather than the shopper's centered column. On small screens the sidebar folds
 * into a horizontal scrolling nav under the top bar.
 */
export function AdminShell({ children }: { children: ReactNode }) {
  const t = useTranslations("nav");
  const tAdmin = useTranslations("admin");
  const tCommon = useTranslations("common");
  const tCatalog = useTranslations("catalog");
  const pathname = usePathname();
  const { data: user } = useCurrentUser();
  const logout = useLogout();

  const items: NavItem[] = [
    { href: "/admin", label: tAdmin("dashboard"), icon: "▦" },
    { href: "/admin/catalog", label: t("catalog"), icon: "📦" },
    { href: "/admin/channels", label: t("channels"), icon: "🏷️" },
    { href: "/admin/access", label: t("access"), icon: "👥" },
    { href: "/admin/orders/new", label: t("manualOrders"), icon: "🧾" },
    { href: "/admin/catalog/import-export", label: tCatalog("navImportExport"), icon: "⇅" },
    { href: "/admin/audit", label: t("audit"), icon: "🔎" },
  ];

  const brand = (
    <Link href="/admin" className="flex items-center gap-2 font-bold tracking-tight text-foreground">
      <span
        aria-hidden
        className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-black text-primary-foreground"
      >
        پ
      </span>
      <span className="flex flex-col leading-tight">
        <span>{tCommon("appName")}</span>
        <span className="text-xs font-normal text-muted-foreground">{tAdmin("title")}</span>
      </span>
    </Link>
  );

  return (
    <div className="flex min-h-screen w-full bg-background">
      {/* Sidebar (lg+) */}
      <aside className="hidden w-64 shrink-0 flex-col gap-6 border-e border-border bg-card p-4 lg:flex">
        <div className="px-2 pt-2">{brand}</div>
        <nav aria-label={tAdmin("menuLabel")} className="flex flex-col gap-1">
          <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {tAdmin("navGroupManage")}
          </p>
          {items.map((item) => (
            <SidebarLink key={item.href} item={item} active={isActive(pathname, item.href)} />
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Admin top bar */}
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-border bg-background/90 px-4 py-3 backdrop-blur">
          <div className="lg:hidden">{brand}</div>
          <div className="hidden text-sm text-muted-foreground lg:block">{tAdmin("dashboardSubtitle")}</div>
          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              {tAdmin("backToStore")}
            </Link>
            <ThemeToggle />
            {user ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => logout.mutate()}
                disabled={logout.isPending}
              >
                {t("logout")}
              </Button>
            ) : null}
          </div>
        </header>

        {/* Mobile nav (horizontal scroller) */}
        <nav
          aria-label={tAdmin("menuLabel")}
          className="flex gap-1 overflow-x-auto border-b border-border bg-card px-3 py-2 lg:hidden"
        >
          {items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "whitespace-nowrap rounded-md px-3 py-1.5 text-sm transition-colors",
                isActive(pathname, item.href)
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <main className="flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}

function SidebarLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
        active
          ? "bg-primary text-primary-foreground"
          : "text-foreground hover:bg-accent hover:text-accent-foreground",
      )}
    >
      <span aria-hidden className="text-base">
        {item.icon}
      </span>
      {item.label}
    </Link>
  );
}
